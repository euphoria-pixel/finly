import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import logging
import os
import random
from uuid import uuid4
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select, func
from .db import *
from .schemas import *
from .services import initialize, dashboard, entities, TransactionIngestionService, emit, notify, check_notifications
from .connectors import CSVStatementParser, ManualStatementConnector, ConnectorError
from . import simulator

load_dotenv(ROOT / '.env')
logger=logging.getLogger('stipendia')
UPLOADS=DATA/'uploads'
UPLOADS.mkdir(exist_ok=True)
MAX_UPLOAD=8*1024*1024
sim_task=None
sync_lock=asyncio.Lock()

async def auto_simulator(interval):
    rng=random.Random(42)
    try:
        while True:
            await asyncio.sleep(interval)
            with Session.begin() as db:
                pending=db.scalar(select(Transaction).where(Transaction.source_type=='personal_simulator',Transaction.status=='pending'))
                if pending: simulator.change_status(db,pending.id,'post')
                cat,merchant,lo,hi=rng.choice(simulator.SHOPS)
                simulator.purchase(db,Purchase(amount_minor=rng.randint(lo,hi),category=cat,merchant=merchant,status='pending'))
    except asyncio.CancelledError:
        pass

async def periodic_sync():
    while True:
        await asyncio.sleep(max(2,int(os.getenv('BANK_POLL_SECONDS','15'))))
        with Session() as db:
            source=db.get(DataSource,'bank_in_a_box')
            enabled=source and source.config.get('polling',False) and db.get(FeatureFlags,USER).demo_pro
        if enabled:
            try: await sync_bank()
            except HTTPException: pass
            except Exception:
                logger.exception('Unexpected sync failure; next poll will retry')

@asynccontextmanager
async def lifespan(app):
    migrate()
    with Session.begin() as db:
        initialize(db)
        source=db.get(DataSource,'personal_simulator')
        if source.status=='running': source.status='ready'
    poll=asyncio.create_task(periodic_sync())
    yield
    poll.cancel()
    if sim_task: sim_task.cancel()
    await asyncio.gather(poll, *([sim_task] if sim_task else []), return_exceptions=True)

app=FastAPI(title='Стипендия · локальный финансовый помощник',version='1.0',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3000','http://localhost:3000'],allow_methods=['GET','POST','PUT','PATCH','DELETE'],allow_headers=['Content-Type'])

@app.middleware('http')
async def local_only(request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:3000','http://localhost:3000','http://127.0.0.1:8000','http://localhost:8000','http://testserver'):
            return JSONResponse({'detail':'Разрешён только локальный интерфейс.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(ValueError)
async def value_error(request,exc):
    return JSONResponse({'detail':str(exc)},status_code=422)

def owned(db,model,id):
    row=db.get(model,id)
    if not row or row.user_id!=USER: raise HTTPException(404,'Запись не найдена')
    return row

@app.get('/api/health')
def health() -> dict:
    return {'status':'ok','mode':'local-single-user-demo','llm_configured':bool(os.getenv('API_KEY'))}

@app.get('/api/dashboard')
@app.get('/api/analytics')
@app.get('/api/budget')
def get_dashboard(scope:Scope='demo',days:int=Query(30,ge=1,le=90)) -> dict:
    with Session() as db: return dashboard(db,scope,days)

@app.get('/api/transactions')
def transactions(scope:Scope='demo',q:str='',category:str='',source:str='',from_date:str='',to_date:str='',
                 min_minor:int|None=None,max_minor:int|None=None,limit:int=Query(500,ge=1,le=5000),offset:int=Query(0,ge=0)) -> dict:
    with Session() as db:
        txs,_=entities(db,scope)
        if q: txs=[t for t in txs if q.lower() in (t.description+' '+(t.merchant_name or '')).lower()]
        if category: txs=[t for t in txs if (t.user_category or t.bank_category)==category]
        if source: txs=[t for t in txs if t.source_type==source]
        if from_date: txs=[t for t in txs if t.occurred_at[:10]>=from_date]
        if to_date: txs=[t for t in txs if t.occurred_at[:10]<=to_date]
        if min_minor is not None: txs=[t for t in txs if abs(t.amount_minor)>=min_minor]
        if max_minor is not None: txs=[t for t in txs if abs(t.amount_minor)<=max_minor]
        txs.sort(key=lambda t:t.occurred_at,reverse=True)
        return {'items':[public(t) for t in txs[offset:offset+limit]],'total':len(txs)}

@app.patch('/api/transactions/{id}')
def patch_transaction(id:str,body:TransactionPatch) -> dict:
    with Session.begin() as db:
        t=owned(db,Transaction,id)
        t.user_category=body.user_category
        t.updated_at=now()
        emit(db,'transaction.updated',{'id':id})
        emit(db,'budget.updated',{})
        return public(t)

@app.get('/api/budget/settings')
def get_settings(scope:Scope='demo') -> Settings:
    with Session() as db: return Settings.model_validate(db.get(BudgetSettings,scope).data)

@app.put('/api/budget/settings')
def save_settings(body:Settings,scope:Scope='demo') -> Settings:
    with Session.begin() as db:
        data=body.model_dump(mode='json')
        old=db.get(BudgetSettings,scope).data
        if body.starting_balance_minor!=old.get('starting_balance_minor') or (body.starting_balance_minor is not None and not old.get('balance_at')):
            data['balance_at']=now()
        else:
            data['balance_at']=old.get('balance_at')
        db.get(BudgetSettings,scope).data=data
        emit(db,'budget.updated',{'scope':scope})
        check_notifications(db,scope)
        return Settings.model_validate(data)

@app.get('/api/recurring')
def get_recurring(scope:Scope='demo') -> list[dict]:
    with Session() as db: return [public(r) for r in db.scalars(select(RecurringPayment).where(RecurringPayment.user_id==USER,RecurringPayment.scope==scope))]

@app.post('/api/recurring')
def add_recurring(body:RecurringInput,scope:Scope='demo') -> dict:
    with Session.begin() as db:
        r=RecurringPayment(scope=scope,**body.model_dump(mode='json'))
        db.add(r); db.flush(); emit(db,'budget.updated',{'scope':scope})
        return public(r)

@app.patch('/api/recurring/{id}')
def update_recurring(id:str,body:RecurringInput) -> dict:
    with Session.begin() as db:
        r=owned(db,RecurringPayment,id)
        for k,v in body.model_dump(mode='json').items():setattr(r,k,v)
        emit(db,'budget.updated',{'scope':r.scope})
        return public(r)

@app.delete('/api/recurring/{id}')
def delete_recurring(id:str) -> ActionResult:
    with Session.begin() as db:
        r=owned(db,RecurringPayment,id); db.delete(r); emit(db,'budget.updated',{})
    return ActionResult()

@app.get('/api/notifications')
def notifications(scope:Scope='demo') -> list[dict]:
    with Session() as db:
        return [public(n) for n in db.scalars(select(Notification).where(Notification.user_id==USER,Notification.scope==scope).order_by(Notification.created_at.desc()).limit(100))]

@app.patch('/api/notifications/{id}')
def read_notification(id:str) -> ActionResult:
    with Session.begin() as db:
        owned(db,Notification,id).read=True
        emit(db,'notification.updated',{'id':id})
    return ActionResult()

@app.get('/api/connections')
def connections() -> list[dict]:
    with Session() as db:
        return [{**public(s),'last_success':db.get(SyncState,s.id).last_success,
                 'error':db.get(SyncState,s.id).error,
                 'accounts':[public(a) for a in db.scalars(select(Account).where(Account.user_id==USER,Account.source_type==s.id))],
                 'transaction_count':db.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id==USER,Transaction.source_type==s.id))} for s in db.scalars(select(DataSource).where(DataSource.user_id==USER,DataSource.id!='tbank_sandbox'))]

@app.post('/api/simulator/seed')
def seed(body:SeedRequest) -> ActionResult:
    with Session.begin() as db: return ActionResult(**simulator.seed_history(db,**body.model_dump()))

@app.post('/api/simulator/transactions')
def purchase(body:Purchase) -> ActionResult:
    with Session.begin() as db: return ActionResult(**simulator.purchase(db,body))

@app.post('/api/simulator/transactions/{id}/{action}')
def simulator_action(id:str,action:Literal['post','cancel','refund']) -> ActionResult:
    with Session.begin() as db: return ActionResult(**simulator.change_status(db,id,action))

@app.post('/api/simulator/start')
async def start_simulator(body:StartRequest) -> ActionResult:
    require_pro()
    global sim_task
    if sim_task and not sim_task.done(): return ActionResult(message='Симулятор уже активен')
    sim_task=asyncio.create_task(auto_simulator(body.interval_seconds))
    with Session.begin() as db:
        s=db.get(DataSource,'personal_simulator');s.status='running';s.config={**s.config,'interval_seconds':body.interval_seconds}
        emit(db,'sync.completed',{'source_type':'personal_simulator','status':'running'})
    return ActionResult(message='Симулятор запущен')

@app.post('/api/simulator/stop')
async def stop_simulator() -> ActionResult:
    global sim_task
    if sim_task: sim_task.cancel(); await sim_task; sim_task=None
    with Session.begin() as db:
        db.get(DataSource,'personal_simulator').status='ready'
        emit(db,'sync.completed',{'source_type':'personal_simulator','status':'ready'})
    return ActionResult(message='Симулятор остановлен')

@app.post('/api/simulator/reset')
async def reset_simulator() -> ActionResult:
    await stop_simulator()
    with Session.begin() as db: simulator.reset(db)
    return ActionResult(message='Операции симулятора удалены; выписки и песочница сохранены')

@app.post('/api/imports')
async def upload_import(file:UploadFile=File(...),is_demo:bool=Form(True),account_id:str=Form('manual-demo')) -> dict:
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ('.csv','.pdf'): raise HTTPException(415,'Поддерживаются PDF и CSV.')
    content=await file.read(MAX_UPLOAD+1)
    if not content or len(content)>MAX_UPLOAD: raise HTTPException(413,'Пустой файл или размер больше 8 МБ.')
    if suffix=='.pdf' and not content.startswith(b'%PDF-'):raise HTTPException(415,'Файл не является PDF.')
    if not account_id.startswith('manual-') or len(account_id)>100:raise HTTPException(422,'Нужен идентификатор счёта с префиксом manual-.')
    job_id=uid(); path=UPLOADS/(job_id+suffix); path.write_bytes(content)
    with Session.begin() as db:
        job=ImportJob(id=job_id,filename=Path(file.filename or "statement").name[:180],path=str(path),is_demo=is_demo,account_id=account_id)
        db.add(job);db.flush()
        try:
            if suffix=='.csv':
                job.rows=CSVStatementParser().parse(content.decode('utf-8-sig'));job.status='preview'
            else:
                # Существующий локальный парсер, без изменений CLI и исходных файлов.
                from main import extract_and_clean_pdf
                job.cleaned_text=await asyncio.to_thread(extract_and_clean_pdf,path)
                job.status='awaiting_approval'
        except Exception:
            job.status='failed';job.error='Не удалось прочитать файл. Проверьте кодировку UTF-8, структуру CSV или текстовый слой PDF.'
        return public(job)

@app.get('/api/imports/{id}')
def get_import(id:str) -> dict:
    with Session() as db:return public(owned(db,ImportJob,id))

async def process_job(id):
    with Session() as db:
        job=owned(db,ImportJob,id);text=job.cleaned_text;path=job.path
    try:
        from main import extract_and_clean_pdf
        from llm_pipeline import analyze_statement, BASE_URL, MODEL
        from openai import OpenAI
        if not text:text=await asyncio.to_thread(extract_and_clean_pdf,path)
        key=os.getenv('API_KEY')
        if not key: raise ValueError('LLM-ключ не настроен. CSV-импорт доступен без ключа.')
        def analyze():
            with OpenAI(api_key=key,base_url=os.getenv('LLM_BASE_URL',BASE_URL),timeout=120,max_retries=0) as client:
                return analyze_statement(client,text,model=os.getenv('LLM_MODEL',MODEL),cache_dir=DATA/'llm_cache')[0]
        result=await asyncio.to_thread(analyze)
        rows=CSVStatementParser().parse(result)
        with Session.begin() as db:
            job=owned(db,ImportJob,id);job.rows=rows;job.status='preview';job.error=None
            emit(db,'import.updated',{'id':id,'status':'preview'})
    except Exception as exc:
        logger.warning('Import processing failed: %s',type(exc).__name__)
        with Session.begin() as db:
            job=owned(db,ImportJob,id);job.status='failed'
            job.error='Обработка LLM не удалась. Документ сохранён; можно повторить. Проверьте ключ и доступность модели.'
            emit(db,'import.updated',{'id':id,'status':'failed'})

@app.post('/api/imports/{id}/process')
async def process_import(id:str,body:ProcessImport,tasks:BackgroundTasks) -> ActionResult:
    if not body.approved:raise HTTPException(422,'Подтвердите отсутствие персональных данных в очищенном тексте.')
    with Session.begin() as db:
        job=owned(db,ImportJob,id)
        if job.status in ('processing','confirmed'):raise HTTPException(409,'Импорт уже обрабатывается или подтверждён.')
        if not job.path.endswith('.pdf'):raise HTTPException(422,'Для CSV используется локальный импорт.')
        job.status='processing';job.error=None
    tasks.add_task(process_job,id)
    return ActionResult(message='Обработка началась')

@app.post('/api/imports/{id}/confirm')
def confirm_import(id:str,body:ConfirmImport) -> ActionResult:
    with Session.begin() as db:
        job=owned(db,ImportJob,id)
        if job.status=='confirmed':return ActionResult(message='Уже импортировано',duplicates=len(job.rows))
        if job.status!='preview':raise HTTPException(409,'Предпросмотр ещё не готов.')
        items=ManualStatementConnector().normalize_rows([r.model_dump() for r in body.rows],job.account_id,job.is_demo)
        if not items:raise HTTPException(422,'Нет выбранных корректных операций.')
        if not db.get(Account,job.account_id):
            db.add(Account(id=job.account_id,source_type='manual_import',name='Счёт из выписки',currency=items[0].currency,is_demo=job.is_demo));db.flush()
        result=TransactionIngestionService(db).ingest(items)
        job.status='confirmed';job.rows=[r.model_dump() for r in body.rows]
        scope='statements' if job.is_demo else 'personal'
        notify(db,scope,'import','Выписка импортирована',f"Добавлено операций: {result['created']}; дубликатов: {result['duplicates']}.",id)
        db.get(SyncState,'manual_import').last_success=now();db.get(DataSource,'manual_import').status='ready'
        emit(db,'sync.completed',{'source_type':'manual_import',**result})
        return ActionResult(**result)

@app.get('/api/events')
async def events(request:Request,after:int=Query(0,ge=0)):
    try: cursor=max(after,int(request.headers.get('last-event-id','0')))
    except ValueError:cursor=after
    async def stream():
        nonlocal cursor
        yield 'retry: 1500\n\n'
        while not await request.is_disconnected():
            with Session() as db:
                rows=list(db.scalars(select(Event).where(Event.user_id==USER,Event.id>cursor).order_by(Event.id).limit(100)))
                for row in rows:
                    cursor=row.id
                    payload=EventPayload(id=row.id,type=row.type,created_at=row.created_at,payload=row.payload)
                    yield f'id: {row.id}\nevent: {row.type}\ndata: {payload.model_dump_json()}\n\n'
            if not rows:yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no','Cache-Control':'no-cache'})

@app.get('/api/events/latest')
def latest_events(after:int=0,tail:bool=False) -> list[EventPayload]:
    with Session() as db:
        query=select(Event).where(Event.user_id==USER,Event.id>after).order_by(Event.id.desc() if tail else Event.id).limit(100)
        rows=list(db.scalars(query))
        return [EventPayload.model_validate(public(e)) for e in (reversed(rows) if tail else rows)]

@app.post('/api/assistant/chat')
async def chat(body:ChatRequest) -> ChatResponse:
    with Session() as db:d=dashboard(db,body.scope)
    from .assistant import rub, explanations
    rendered=explanations(d)
    if 'недел' in body.message.lower():
        with Session() as db:week=dashboard(db,body.scope,7)
        top=week['categories'][:3]
        answer='За неделю расходы: '+rub(week['expense_minor'])+'. '+('; '.join(x['name']+': '+rub(x['amount_minor']) for x in top) or 'Операций пока нет.')
    elif any(w in body.message.lower() for w in ('уменьш','измен','вырос','покупк')):
        answer=rendered['change']+' '+rendered['budget']
    elif any(w in body.message.lower() for w in ('куда','категор','уходят')):
        answer=rendered['categories']
    elif any(w in body.message.lower() for w in ('платеж','платёж','регуляр')):
        answer='Ожидаемые обязательные платежи: '+rub(d['obligations_minor'])+'. '+', '.join(r['name'] for r in d['recurring'])
    else:
        answer=f"До следующего поступления {d['days_remaining']} дн. Доступный бюджет: {rub(d['available_minor'])}. Дневной лимит: {rub(d['daily_limit_minor'])}. Прогноз перед поступлением: {rub(d['forecast_minor'])}. "
        answer+=('Укажите известный остаток в настройках, чтобы рассчитать прогноз.' if d['balance_minor'] is None else 'Это оценка по известным операциям и текущему темпу расходов, а не гарантия.')
    if not body.use_llm or not os.getenv('API_KEY'):return ChatResponse(answer=answer,mode='local')
    from .assistant import explanations, select_explanations
    facts={k:d[k] for k in ('balance_minor','available_minor','daily_limit_minor','forecast_minor','days_remaining','week_expense_minor','obligations_minor','reserve_minor','pace_minor')}
    try:
        keys=await asyncio.to_thread(select_explanations,body.message,facts)
        rendered=explanations(d)
        return ChatResponse(answer=' '.join(rendered[k] for k in keys),mode='llm')
    except Exception:
        return ChatResponse(answer=answer+' LLM сейчас недоступна; показано локальное объяснение.',mode='local')


from .bank_in_a_box import BankInABoxConnector

def require_pro():
    with Session() as db:
        if not db.get(FeatureFlags,USER).demo_pro:raise HTTPException(403,'Включите демонстрационный Pro на странице тарифов. Оплата не нужна.')

@app.get('/api/plan')
def get_plan():
    with Session() as db:return {'demo_pro':db.get(FeatureFlags,USER).demo_pro}

@app.post('/api/plan')
async def set_plan(enabled:bool=False):
    async with sync_lock:
        with Session.begin() as db:
            db.get(FeatureFlags,USER).demo_pro=enabled
            if not enabled:
                source=db.get(DataSource,'bank_in_a_box')
                source.config={**source.config,'polling':False}
            emit(db,'budget.updated',{'plan_changed':True})
    if not enabled:await stop_simulator()
    return {'demo_pro':enabled,'message':'Демонстрационный Pro включён' if enabled else 'Free включён. История сохранена, автоматизация остановлена.'}

@app.post('/api/connections/bank-in-a-box/test')
async def test_bank():
    require_pro()
    try:return await BankInABoxConnector().test_connection()
    except ConnectorError as exc:raise HTTPException(502,str(exc))

@app.post('/api/connections/bank-in-a-box/sync')
async def sync_bank():
    async with sync_lock:
        require_pro()
        try:
            connector=BankInABoxConnector()
            snapshots=await connector.snapshot()
            items=[connector.normalize_transaction(t) for snap in snapshots for t in snap['transactions']]
            with Session.begin() as db:
                active=set()
                for snap in snapshots:
                    raw=snap['account'];bal=snap['balance'];ident='biab:'+raw['accountId'];active.add(ident)
                    account=db.get(Account,ident)
                    if account and account.user_id!=USER:raise ConnectorError('Конфликт владельца счёта.')
                    if not account:
                        account=Account(id=ident,source_type='bank_in_a_box',name=raw.get('nickname') or raw['accountId'],currency=raw['currency'],is_demo=True)
                        db.add(account)
                    if bal['amount']['currency']!=account.currency:raise ConnectorError('Валюты баланса и счёта не совпадают.')
                    account.balance_minor=money_minor(bal['amount']['amount'],account.currency)*( -1 if bal.get('creditDebitIndicator')=='Debit' else 1)
                    account.balance_at=datetime.fromisoformat(bal['dateTime'].replace('Z','+00:00')).isoformat()
                for old in db.scalars(select(Account).where(Account.user_id==USER,Account.source_type=='bank_in_a_box')):
                    if old.id not in active:old.balance_minor=None;old.balance_at=None
                db.flush()
                counts=TransactionIngestionService(db).ingest(items)
                state=db.get(SyncState,'bank_in_a_box');state.last_success=now();state.error=None
                state.cursor=state.last_success
                state.raw_response=json.loads(json.dumps({'snapshots':snapshots},default=str))
                source=db.get(DataSource,'bank_in_a_box');source.status='connected'
                source.config={**source.config,'polling':True,'interval_seconds':max(2,int(os.getenv('BANK_POLL_SECONDS','15')))}
                for scope in ('demo','bank','combined'):
                    check_notifications(db,scope)
                    emit(db,'budget.updated',{'scope':scope})
                emit(db,'sync.completed',{'source_type':'bank_in_a_box',**counts})
                return {**counts,'ok':True,'last_success':state.last_success,'message':'Счета, балансы и история получены из локального Bank-in-a-Box'}
        except (ConnectorError,ValueError,KeyError,TypeError) as exc:
            message=str(exc) if isinstance(exc,ConnectorError) else 'Некорректные данные учебного банка. Сохранённая история доступна.'
            with Session.begin() as db:
                db.get(DataSource,'bank_in_a_box').status='error'
                db.get(SyncState,'bank_in_a_box').error=message
                notify(db,'demo','sync_error','Ошибка синхронизации',message,datetime.now(timezone.utc).date().isoformat())
                emit(db,'sync.failed',{'source_type':'bank_in_a_box','message':message})
            raise HTTPException(502,message)

@app.post('/api/connections/bank-in-a-box/polling')
async def bank_polling(enabled:bool=False):
    async with sync_lock:
        if enabled:require_pro()
        with Session.begin() as db:
            s=db.get(DataSource,'bank_in_a_box');s.config={**s.config,'polling':enabled}
            emit(db,'sync.completed',{'source_type':s.id,'polling':enabled})
    return {'ok':True,'message':'Опрос включён' if enabled else 'Опрос выключен, история сохранена'}

@app.post('/api/simulator/scenario')
def replay_scenario():
    require_pro()
    with Session.begin() as db:
        results=[]
        for ident,amount,category,merchant in [('coffee',25000,'Кафе и доставка','Сценарий: кофе'),('bus',6000,'Транспорт','Сценарий: автобус'),('large',1200000,'Покупки','Сценарий: ноутбук')]:
            results.append(simulator.purchase(db,Purchase(amount_minor=amount,category=category,merchant=merchant),external_id='scenario-'+ident))
    return {'ok':True,'message':'Сценарий воспроизведён: кофе, транспорт, крупная покупка','created':sum(r['created'] for r in results)}

@app.post('/api/demo/reset')
async def reset_demo():
    await stop_simulator()
    with Session.begin() as db:
        simulator.reset(db)
        from sqlalchemy import delete
        db.execute(delete(RecurringPayment).where(RecurringPayment.user_id==USER,RecurringPayment.scope=='demo'))
        db.get(BudgetSettings,'demo').data=Settings(next_income_date=datetime.now(timezone.utc).date()+timedelta(days=12)).model_dump(mode='json')
        simulator.seed_history(db,days=30,seed=42,profile='parttime')
    return {'ok':True,'message':'Сценарий восстановлен. Выписки и банковская история сохранены.'}
