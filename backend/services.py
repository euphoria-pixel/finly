from datetime import datetime, timezone, timedelta
import json
from sqlalchemy import select
from .db import Transaction, Account, BudgetSettings, RecurringPayment, Notification, Event, DataSource, SyncState, FeatureFlags, ImportJob, USER, now, public
from .schemas import Settings, TransactionInput
from .budget import calculate


def emit(db, kind, payload):
    db.add(Event(type=kind, payload=payload))


def initialize(db):
    if not db.get(FeatureFlags,USER):db.add(FeatureFlags(user_id=USER,demo_pro=False))
    for kind, name in [('manual_import','Импорт выписки'),('personal_simulator','Личная демо-карта'),('bank_in_a_box','Кампус · Bank-in-a-Box')]:
        if not db.get(DataSource,kind): db.add(DataSource(id=kind,name=name,config={}))
        if not db.get(SyncState,kind): db.add(SyncState(id=kind))
    for scope in ('demo','personal','sandbox','combined','bank','statements'):
        if not db.get(BudgetSettings, scope):
            data = Settings(next_income_date=datetime.now(timezone.utc).date()+timedelta(days=12)).model_dump(mode='json')
            db.add(BudgetSettings(id=scope,data=data))
    db.flush()


def scope_matches(t, scope):
    if scope=='statements': return t.source_type=='manual_import' and t.is_demo
    if scope=='bank': return t.source_type=='bank_in_a_box'
    if scope=='sandbox': return t.source_type=='tbank_sandbox'
    if scope=='combined': return t.is_demo
    if scope=='personal': return not t.is_demo
    return t.is_demo and t.source_type in ('bank_in_a_box','personal_simulator')


def entities(db, scope):
    txs = [t for t in db.scalars(select(Transaction).where(Transaction.user_id==USER)) if scope_matches(t,scope)]
    accounts = [a for a in db.scalars(select(Account).where(Account.user_id==USER)) if scope_matches(a,scope)]
    return txs,accounts


def dashboard(db, scope='demo', days=30):
    txs, accounts = entities(db,scope)
    settings = db.get(BudgetSettings,scope).data
    recurring = [public(r) for r in db.scalars(select(RecurringPayment).where(RecurringPayment.user_id==USER,RecurringPayment.scope==scope))]
    data = calculate([{**public(t),'raw_payload':t.raw_payload} for t in txs], [public(a) for a in accounts], settings, recurring, period_days=days)
    for t in data['largest']: t.pop('raw_payload',None)
    imports=list(db.scalars(select(ImportJob).where(ImportJob.user_id==USER,ImportJob.status=='confirmed')))
    data['last_import_at']=max((j.created_at for j in imports if j.is_demo==(scope!='personal')),default=None)
    data['demo_pro']=bool(db.get(FeatureFlags,USER).demo_pro)
    state=db.get(SyncState,'bank_in_a_box')
    data['last_bank_sync']=state.last_success if state else None
    data.update(scope=scope,transactions=[public(t) for t in sorted(txs,key=lambda t:t.occurred_at,reverse=True)[:8]],
                accounts=[public(a) for a in accounts],settings=settings,
                transaction_count=len(txs),unread_count=sum(1 for n in db.scalars(select(Notification).where(Notification.scope==scope,Notification.user_id==USER,Notification.read==False))))
    return data


def notify(db, scope, kind, title, message, key):
    settings=db.get(BudgetSettings,scope)
    if settings and (not settings.data.get('notifications_enabled',True) or kind in settings.data.get('disabled_rules',[])): return
    key=f'{scope}:{kind}:{key}'
    if db.scalar(select(Notification).where(Notification.dedupe_key==key)): return
    n=Notification(scope=scope,kind=kind,title=title,message=message,dedupe_key=key,is_demo=scope!='personal')
    db.add(n)
    db.flush()
    emit(db,'notification.created',{'id':n.id,'scope':scope,'title':title})


def check_notifications(db,scope,changed=None):
    d=dashboard(db,scope)
    today=datetime.now(timezone.utc).date().isoformat()
    if d['daily_limit_minor'] is not None and d['today_expense_minor']>d['daily_limit_minor']:
        notify(db,scope,'daily','Дневной бюджет превышен','Сегодня расходы выше безопасного дневного лимита.',today)
    pct=d['month_expense_minor']*100//d['monthly_limit_minor']
    if pct>=80:
        threshold=100 if pct>=100 else 80
        notify(db,scope,'monthly',f'Использовано {threshold}% месячного лимита','Проверьте оставшийся бюджет на месяц.',today[:7]+str(threshold))
    if d['forecast_minor'] is not None and d['forecast_minor']<0:
        notify(db,scope,'forecast','До стипендии может не хватить денег','При текущем темпе расходов прогноз отрицательный.',d['next_income_date'])
    if changed and changed.status=='posted' and changed.direction=='expense' and changed.amount_minor<0:
        threshold=max(300000, (d['pace_minor'] or 0)*3)
        if -changed.amount_minor>=threshold:
            notify(db,scope,'large','Крупная покупка','Новая операция существенно выше обычных ежедневных расходов.',changed.id)


class TransactionIngestionService:
    def __init__(self, db): self.db=db
    def ingest(self, items, *, notify_rules=True):
        db=self.db
        counts={'created':0,'updated':0,'duplicates':0}
        changed=[]
        for item in items:
            item=TransactionInput.model_validate(item)
            values=item.model_dump(mode='json')
            account=db.get(Account,item.account_id)
            if not account or account.user_id!=USER or account.source_type!=item.source_type or account.is_demo!=item.is_demo:
                raise ValueError('Счёт не соответствует источнику операции.')
            existing=db.scalar(select(Transaction).where(Transaction.user_id==USER,Transaction.account_id==item.account_id,
                Transaction.source_type==item.source_type,Transaction.external_id==item.external_id))
            if existing:
                # Пользовательская категория имеет приоритет перед повторным импортом.
                values['user_category']=existing.user_category or item.user_category
                if all(getattr(existing,k)==v for k,v in values.items()):
                    counts['duplicates']+=1
                    continue
                for k,v in values.items(): setattr(existing,k,v)
                existing.updated_at=now()
                tx=existing
                counts['updated']+=1
                kind='transaction.updated'
            else:
                tx=Transaction(**values)
                db.add(tx)
                counts['created']+=1
                kind='transaction.created'
            db.flush()
            changed.append(tx)
            emit(db,kind,{'id':tx.id,'source_type':tx.source_type,'is_demo':tx.is_demo})
        if changed:
            db.flush()
            scopes=set('sandbox' if t.source_type=='tbank_sandbox' else 'demo' if t.is_demo else 'personal' for t in changed)
            if any(t.is_demo for t in changed): scopes.add('combined')
            if any(t.source_type=='bank_in_a_box' for t in changed): scopes.add('bank')
            if any(t.source_type=='manual_import' and t.is_demo for t in changed): scopes.add('statements')
            for scope in scopes:
                emit(db,'budget.updated',{'scope':scope})
                if notify_rules:
                    check_notifications(db,scope)
                    for tx in changed:
                        if scope_matches(tx,scope): check_notifications(db,scope,tx)
        return counts
