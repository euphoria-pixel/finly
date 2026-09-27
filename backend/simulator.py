from datetime import datetime, timedelta, timezone
import random
from uuid import uuid4
from sqlalchemy import select, delete
from .db import Account, Transaction, Notification, Event, BudgetSettings, RecurringPayment, DataSource, SyncState, now, USER
from .schemas import Purchase, TransactionInput
from .services import TransactionIngestionService, emit, check_notifications

SHOPS=[('Продукты','Маркет «У дома»',18000,95000),('Кафе и доставка','Кофейня «Перемена»',16000,65000),
       ('Транспорт','Городской транспорт',4000,16000),('Покупки','Маркетплейс «Полка»',40000,180000),
       ('Развлечения','Кино «Спутник»',25000,70000),('Связь','Мобильная связь',40000,60000),
       ('Подписки','Музыка+',19900,39900),('Учёба','Книжный кампус',15000,80000),('Здоровье','Аптека',15000,90000),('Другое','Разное',5000,50000)]

def ensure_accounts(db, baseline=None):
    for account_id,name,balance in [('sim-main','Карта студента',3000000),('sim-save','Копилка',800000)]:
        if not db.get(Account,account_id):
            db.add(Account(id=account_id,source_type='personal_simulator',name=name,currency='RUB',
                balance_minor=balance,balance_at=baseline or now(),is_demo=True))
    db.flush()


class DemoTransactionConnector:
    """Separate synthetic source; never writes to Bank-in-a-Box balances."""
    @staticmethod
    def ingest(db, items):
        return TransactionIngestionService(db).ingest(items)

def purchase(db, request:Purchase, external_id=None, at=None):
    ensure_accounts(db)
    at=at or now()
    ext=external_id or str(uuid4())
    existing=db.scalar(select(Transaction).where(Transaction.user_id==USER,Transaction.account_id==request.account_id,Transaction.source_type=='personal_simulator',Transaction.external_id==ext))
    if existing:return {'created':0,'updated':0,'duplicates':1}
    tx=TransactionInput(external_id=ext,account_id=request.account_id,source_type='personal_simulator',
        source_name='Симулятор личной карты',occurred_at=at,posted_at=at if request.status=='posted' else None,
        amount_minor=request.amount_minor*(1 if request.direction=='income' else -1),currency='RUB',
        direction=request.direction,description=request.merchant,merchant_name=request.merchant,
        bank_category=request.category,status=request.status,is_demo=True,raw_payload={'synthetic':True})
    items=[tx]
    if request.direction=='transfer':
        other='sim-save' if request.account_id=='sim-main' else 'sim-main'
        items.append(tx.model_copy(update={'external_id':ext+'-credit','account_id':other,'amount_minor':request.amount_minor}))
    result=DemoTransactionConnector.ingest(db,items)
    return result


def seed_history(db, days=30, seed=42, profile='parttime'):
    today=datetime.now(timezone.utc).replace(hour=12,minute=0,second=0,microsecond=0)
    baseline=(today-timedelta(days=days)).isoformat()
    ensure_accounts(db,baseline)
    rng=random.Random(seed)
    items=[]
    for offset in range(days):
        at=(today-timedelta(days=days-1-offset)).isoformat()
        for index in range(rng.randint(1,3)):
            cat,merchant,lo,hi=rng.choice(SHOPS)
            amount=rng.randint(lo//100,hi//100)*100
            items.append(TransactionInput(external_id=f'history-{seed}-{profile}-{days}-{offset}-{index}',account_id='sim-main',source_type='personal_simulator',
                source_name='Симулятор личной карты',occurred_at=at,posted_at=at,amount_minor=-amount,currency='RUB',direction='expense',
                description=merchant,merchant_name=merchant,bank_category=cat,status='posted',is_demo=True,raw_payload={'synthetic':True,'seed':seed}))
        if offset%30==0 or (profile=='parttime' and offset%15==0) or (profile=='irregular' and offset%9==0):
            amount=800000 if offset%30==0 else 1400000 if profile=='parttime' else rng.randint(4000,12000)*100
            label='Стипендия' if offset%30==0 else 'Подработка'
            items.append(TransactionInput(external_id=f'income-{seed}-{profile}-{days}-{offset}',account_id='sim-main',source_type='personal_simulator',
                source_name='Симулятор личной карты',occurred_at=at,posted_at=at,amount_minor=amount,currency='RUB',direction='income',
                description=label,bank_category='Доход',status='posted',is_demo=True,raw_payload={'synthetic':True,'seed':seed}))
    result=TransactionIngestionService(db).ingest(items,notify_rules=False)
    if not db.scalar(select(RecurringPayment).where(RecurringPayment.scope=='demo')):
        db.add(RecurringPayment(scope='demo',name='Связь и интернет',amount_minor=65000,due_date=(today+timedelta(days=4)).date().isoformat()))
        db.add(RecurringPayment(scope='demo',name='Общежитие',amount_minor=180000,due_date=(today+timedelta(days=8)).date().isoformat()))
    source=db.get(DataSource,'personal_simulator')
    source.status='ready'
    source.config={**source.config,'profile':profile,'seed':seed,'days':days}
    db.get(SyncState,'personal_simulator').last_success=now()
    db.flush()
    check_notifications(db,'demo')
    emit(db,'sync.completed',{'source_type':'personal_simulator',**result})
    return result


def change_status(db, tx_id, action):
    tx=db.get(Transaction,tx_id)
    if not tx or tx.user_id!=USER or tx.source_type!='personal_simulator': raise ValueError('Операция симулятора не найдена.')
    data={k:getattr(tx,k) for k in TransactionInput.model_fields}
    if action=='refund':
        if tx.status!='posted' or tx.direction!='expense' or tx.amount_minor>=0:
            raise ValueError('Возврат доступен только для проведённой покупки.')
        data.update(external_id=tx.external_id+'-refund',amount_minor=-tx.amount_minor,
                    description='Возврат: '+tx.description,occurred_at=now(),posted_at=now())
        # Стабильные даты обеспечивают идемпотентный повтор возврата.
        existing=db.scalar(select(Transaction).where(Transaction.external_id==data['external_id'],Transaction.account_id==tx.account_id))
        if existing: return {'created':0,'updated':0,'duplicates':1}
    elif action=='post':
        if tx.status=='reversed': raise ValueError('Отменённую операцию нельзя провести.')
        data.update(status='posted',posted_at=tx.posted_at or now())
    else:
        refunded=db.scalar(select(Transaction).where(Transaction.external_id==tx.external_id+'-refund',Transaction.account_id==tx.account_id,Transaction.status=='posted'))
        if refunded: raise ValueError('Покупка уже возвращена; отмените возврат перед отменой исходной операции.')
        data.update(status='reversed')
    items=[TransactionInput.model_validate(data)]
    if tx.direction=='transfer':
        base=tx.external_id.removesuffix('-credit')
        peer=db.scalar(select(Transaction).where(Transaction.external_id==(base if tx.external_id.endswith('-credit') else base+'-credit')))
        if peer:
            peer_data={k:getattr(peer,k) for k in TransactionInput.model_fields}
            peer_data.update(status=data['status'],posted_at=data['posted_at'])
            items.append(TransactionInput.model_validate(peer_data))
    return TransactionIngestionService(db).ingest(items)


def reset(db):
    db.execute(delete(Transaction).where(Transaction.user_id==USER,Transaction.source_type=='personal_simulator'))
    db.execute(delete(Account).where(Account.user_id==USER,Account.source_type=='personal_simulator'))
    db.execute(delete(Notification).where(Notification.user_id==USER,Notification.scope.in_(['demo','combined'])))
    source=db.get(DataSource,'personal_simulator')
    source.status='idle'
    source.config={}
    db.get(SyncState,'personal_simulator').last_success=None
    emit(db,'budget.updated',{'scope':'demo','reset':True})
