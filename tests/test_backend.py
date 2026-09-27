import asyncio
from datetime import datetime,timezone,timedelta
import httpx
import pytest
from backend.budget import calculate
from backend.db import Session,Transaction,Event
from backend.schemas import Settings
from sqlalchemy import select,func
CSV='дата,описание,сумма,валюта,категория\n26.09.2026,Демо-кафе,-125.50,RUB,Кафе\n26.09.2026,Демо-кафе,-125.50,RUB,Кафе\n'
BANK={'operationId':'test-operation','operationDate':'2026-09-26T10:00:00Z','operationAmount':'123.45','operationCurrencyDigitalCode':'643','typeOfOperation':'Debit','operationStatus':'Authorization','description':'Тестовая покупка'}
def upload(c,text=CSV,name='test.csv'):
    return c.post('/api/imports',files={'file':(name,text.encode(),'text/csv')})
def confirm(c,job):
    rows=[{k:v for k,v in r.items() if k!='error'} for r in job['rows']]
    return c.post('/api/imports/'+job['id']+'/confirm',json={'rows':rows})
def test_csv_import_duplicates_and_identical_operations(client):
    job=upload(client).json()
    assert job['status']=='preview'
    result=confirm(client,job)
    assert result.status_code==200,result.text
    assert result.json()['created']==2
    assert confirm(client,upload(client).json()).json()['duplicates']==2
    assert client.get('/api/transactions?scope=statements').json()['total']==2

def test_invalid_files_and_suspicious_rows(client):
    assert upload(client,'bad','evil.exe').status_code==415
    assert upload(client,'not pdf','evil.pdf').status_code==415
    assert upload(client,'bad').json()['status']=='failed'
    job=upload(client,CSV.replace('-125.50','oops')).json()
    assert job['rows'][0]['error']
    assert confirm(client,job).status_code==422
    assert client.get('/api/transactions').json()['total']==0

def test_purchase_budget_notification_events_refund_transfer(client):
    assert client.post('/api/simulator/seed',json={}).status_code==200
    old=client.get('/api/dashboard').json()
    purchase=client.post('/api/simulator/transactions',json={'amount_minor':9000000,'merchant':'Синтетическая большая покупка'})
    assert purchase.status_code==200,purchase.text
    new=client.get('/api/dashboard').json()
    assert new['balance_minor']==old['balance_minor']-9000000
    assert new['forecast_minor']<0 and new['deficit_minor']>0
    notifications=client.get('/api/notifications').json()
    assert {'daily','large','forecast'}.issubset({n['kind'] for n in notifications})
    before=len(notifications)
    client.post('/api/simulator/transactions',json={'amount_minor':100})
    assert len(client.get('/api/notifications').json())==before
    events=client.get('/api/events/latest').json()
    assert any(e['type']=='transaction.created' for e in events)
    with Session() as db:id=db.scalar(select(Transaction).where(Transaction.description=='Синтетическая большая покупка')).id
    assert client.post(f'/api/simulator/transactions/{id}/refund').json()['created']==1
    assert client.post(f'/api/simulator/transactions/{id}/refund').json()['duplicates']==1
    refunded=client.get('/api/dashboard').json()
    assert refunded['expense_minor']==old['expense_minor']+100
    assert client.post('/api/simulator/transactions',json={'amount_minor':20000,'direction':'transfer'}).json()['created']==2
    after=client.get('/api/dashboard').json()
    assert after['balance_minor']==refunded['balance_minor']
    assert after['expense_minor']==refunded['expense_minor']

def test_pending_post_cancel(client):
    client.post('/api/simulator/seed',json={})
    old=client.get('/api/dashboard').json()
    client.post('/api/simulator/transactions',json={'amount_minor':10000,'status':'pending','merchant':'HOLD'})
    d=client.get('/api/dashboard').json()
    assert d['balance_minor']==old['balance_minor'] and d['pending_minor']==10000
    tx=next(t for t in client.get('/api/transactions').json()['items'] if t['description']=='HOLD')
    client.post('/api/simulator/transactions/'+tx['id']+'/post')
    d=client.get('/api/dashboard').json()
    assert d['balance_minor']==old['balance_minor']-10000 and d['pending_minor']==0
    client.post('/api/simulator/transactions/'+tx['id']+'/cancel')
    assert client.get('/api/dashboard').json()['balance_minor']==old['balance_minor']

def test_unknown_balance_and_settings(client):
    assert client.get('/api/dashboard').json()['balance_minor'] is None
    settings=client.get('/api/budget/settings').json()
    settings['starting_balance_minor']=100000;settings['reserve_minor']=200000
    assert client.put('/api/budget/settings',json=settings).status_code==200
    data=client.get('/api/dashboard').json()
    assert data['available_minor']==-100000 and data['daily_limit_minor']==0
    assert data['forecast_minor'] is None

def test_notification_preferences_and_isolation(client):
    client.post('/api/simulator/seed',json={})
    settings=client.get('/api/budget/settings').json();settings['notifications_enabled']=False
    client.put('/api/budget/settings',json=settings)
    before=len(client.get('/api/notifications').json())
    client.post('/api/simulator/transactions',json={'amount_minor':9000000})
    assert len(client.get('/api/notifications').json())==before
    assert client.get('/api/transactions?scope=personal').json()['total']==0
    assert client.post('/api/simulator/transactions',json={},headers={'Origin':'https://evil.example'}).status_code==403

def test_budget_boundary_and_foreign_currency():
    today=datetime.now(timezone.utc).date()
    settings=Settings(next_income_date=today+timedelta(days=10),reserve_minor=10000).model_dump(mode='json')
    settings['starting_balance_minor']=100000;settings['balance_at']=datetime.now(timezone.utc).isoformat()
    base={'occurred_at':today.isoformat()+'T00:00:00+00:00','status':'posted','direction':'expense','amount_minor':-2000,'currency':'RUB','account_id':'a'}
    d=calculate([base,{**base,'currency':'USD','amount_minor':-90000}],[],settings,[])
    assert d['daily_limit_minor']==9000 and d['expense_minor']==2000
    assert d['totals_by_currency']['USD']['expense_minor']==90000 and d['forecast_minor']==80000
    settings['next_income_date']=today.isoformat()
    assert calculate([],[],settings,[])['days_remaining']==0
    assert calculate([],[],settings,[])['forecast_minor'] is None

def test_local_assistant(client):
    r=client.post('/api/assistant/chat',json={'message':'Хватит ли мне денег?','use_llm':False})
    assert r.status_code==200 and r.json()['mode']=='local' and 'неизвестно' in r.json()['answer']
