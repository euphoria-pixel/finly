import asyncio
import copy
from datetime import datetime,timezone
import httpx
import pytest
from backend.bank_in_a_box import BankInABoxConnector
from backend.connectors import ConnectorError

TX={'accountId':'acc-1','transactionId':'test-bank-tx','amount':{'amount':'123.45','currency':'RUB'},'creditDebitIndicator':'Debit','status':'pending','bookingDateTime':'2026-09-25T10:00:00Z','transactionInformation':'Кофе','merchant':{'name':'Кампус','mccCode':'5812','category':'Кафе'},'future_field':{'preserved':True}}

def bank_transport(tx=None, failure=None):
    tx=tx or TX
    def handler(req):
        if failure=='timeout':raise httpx.ReadTimeout('test',request=req)
        if failure=='auth':return httpx.Response(401,json={})
        if failure=='json':return httpx.Response(200,text='oops')
        if req.url.path=='/auth/login':return httpx.Response(200,json={'access_token':'backend-secret','client_id':'demo-student'})
        assert req.headers['authorization']=='Bearer backend-secret'
        if req.url.path=='/accounts':return httpx.Response(200,json={'data':{'account':[{'accountId':'acc-1','nickname':'Личная карта','currency':'RUB'}]}})
        if req.url.path.endswith('/balances'):return httpx.Response(200,json={'data':{'balance':[{'accountId':'acc-1','type':'InterimBooked','dateTime':datetime.now(timezone.utc).isoformat(),'amount':{'amount':'1000.00','currency':'RUB'},'creditDebitIndicator':'Credit'}]}})
        return httpx.Response(200,json={'data':{'transaction':[tx]},'meta':{'totalPages':1},'links':{}})
    return httpx.MockTransport(handler)

def test_normalization():
    c=BankInABoxConnector();t=c.normalize_transaction(TX)
    assert (t.amount_minor,t.status,t.mcc)==(-12345,'pending','5812')
    assert t.raw_payload['future_field']=={'preserved':True}
    assert c.normalize_transaction({**TX,'status':'unexpected'}).status=='unknown'
    with pytest.raises(ConnectorError):c.normalize_transaction({'transactionId':'bad'})
    refund=c.normalize_transaction({**TX,'creditDebitIndicator':'Credit','transactionInformation':'Возврат покупки','status':'Booked'})
    assert refund.direction=='expense' and refund.amount_minor==12345

@pytest.mark.parametrize('failure',['timeout','auth','json'])
def test_errors(failure,monkeypatch):
    monkeypatch.setenv('BIAB_PASSWORD','password')
    with pytest.raises(ConnectorError):asyncio.run(BankInABoxConnector(bank_transport(failure=failure)).snapshot())

def test_sync_and_status(client,monkeypatch):
    monkeypatch.setenv('BIAB_PASSWORD','password')
    current=copy.deepcopy(TX)
    monkeypatch.setattr('backend.app.BankInABoxConnector',lambda:BankInABoxConnector(bank_transport(current)))
    assert client.post('/api/connections/bank-in-a-box/sync').status_code==403
    client.post('/api/plan?enabled=true')
    first=client.post('/api/connections/bank-in-a-box/sync')
    assert first.status_code==200,first.text
    assert first.json()['created']==1
    assert client.post('/api/connections/bank-in-a-box/sync').json()['duplicates']==1
    current['status']='Booked'
    assert client.post('/api/connections/bank-in-a-box/sync').json()['updated']==1
    d=client.get('/api/dashboard?scope=bank').json()
    assert d['balance_minor']==100000 # booked balance already includes the transaction
    tx=client.get('/api/transactions?scope=bank').json()['items'][0]
    assert tx['source_transaction_id']=='test-bank-tx' and tx['status']=='posted'
    assert 'raw_payload' not in tx and 'backend-secret' not in client.get('/api/connections').text
    client.post('/api/plan?enabled=false')
    assert client.get('/api/transactions?scope=bank').json()['total']==1
    assert client.post('/api/simulator/start',json={}).status_code==403
    assert not next(c for c in client.get('/api/connections').json() if c['id']=='bank_in_a_box')['config']['polling']

def test_failed_sync_keeps_data_and_dedupes_warning(client,monkeypatch):
    client.post('/api/plan?enabled=true')
    monkeypatch.setenv('BIAB_PASSWORD','password')
    monkeypatch.setattr('backend.app.BankInABoxConnector',lambda:BankInABoxConnector(bank_transport()))
    client.post('/api/connections/bank-in-a-box/sync')
    monkeypatch.setattr('backend.app.BankInABoxConnector',lambda:BankInABoxConnector(bank_transport(failure='timeout')))
    for _ in range(2):assert client.post('/api/connections/bank-in-a-box/sync').status_code==502
    assert client.get('/api/transactions?scope=bank').json()['total']==1
    assert len([n for n in client.get('/api/notifications').json() if n['kind']=='sync_error'])==1
    connection=next(c for c in client.get('/api/connections').json() if c['id']=='bank_in_a_box')
    assert connection['last_success'] and connection['status']=='error'

def test_account_allowlist(monkeypatch):
    c=BankInABoxConnector()
    with pytest.raises(ConnectorError):asyncio.run(c.get_balances('acc-999'))
    monkeypatch.setenv('BIAB_BASE_URL','http://evil.example')
    with pytest.raises(ConnectorError):BankInABoxConnector()

def test_scenario_reset_and_idempotency(client):
    client.post('/api/plan?enabled=true')
    client.post('/api/demo/reset')
    before=client.get('/api/dashboard').json()
    assert client.post('/api/simulator/scenario').json()['created']==3
    assert client.post('/api/simulator/scenario').json()['created']==0
    after=client.get('/api/dashboard').json()
    assert after['balance_minor']==before['balance_minor']-1231000
    assert after['daily_limit_minor']<before['daily_limit_minor']
    assert any(n['kind']=='daily' for n in client.get('/api/notifications').json())
    client.post('/api/demo/reset')
    assert client.get('/api/dashboard').json()['balance_minor']==before['balance_minor']

def test_llm_unavailable(client,monkeypatch):
    monkeypatch.setenv('API_KEY','synthetic-test-key')
    def fail(*args):raise RuntimeError('offline')
    monkeypatch.setattr('backend.assistant.select_explanations',fail)
    result=client.post('/api/assistant/chat',json={'message':'Хватит ли денег?','use_llm':True}).json()
    assert result['mode']=='local' and 'недоступна' in result['answer']

def test_pdf_pipeline_and_failure(client,monkeypatch):
    from pathlib import Path
    import llm_pipeline
    monkeypatch.setenv('API_KEY','synthetic-test-key')
    csv='дата,описание,сумма,валюта,категория\n26.09.2026,Демо-кофе,-250.00,RUB,Кафе\n'
    monkeypatch.setattr(llm_pipeline,'analyze_statement',lambda *a,**k:(csv,{}))
    def upload():
        return client.post('/api/imports',files={'file':('demo.pdf',Path('fixtures/demo-statement.pdf').read_bytes(),'application/pdf')}).json()
    job=upload()
    assert job['status']=='awaiting_approval',job
    assert client.post('/api/imports/'+job['id']+'/process',json={'approved':False}).status_code==422
    assert client.post('/api/imports/'+job['id']+'/process',json={'approved':True}).status_code==200
    preview=client.get('/api/imports/'+job['id']).json()
    assert preview['status']=='preview'
    rows=[{k:v for k,v in r.items() if k!='error'} for r in preview['rows']]
    assert client.post('/api/imports/'+job['id']+'/confirm',json={'rows':rows}).json()['created']==1
    def fail(*a,**k):raise RuntimeError('offline')
    monkeypatch.setattr(llm_pipeline,'analyze_statement',fail)
    second=upload()
    client.post('/api/imports/'+second['id']+'/process',json={'approved':True})
    assert client.get('/api/imports/'+second['id']).json()['status']=='failed'
    assert client.get('/api/dashboard?scope=statements').json()['transaction_count']==1

def test_pagination(monkeypatch):
    monkeypatch.setenv('BIAB_PASSWORD','password')
    seen=[]
    original=bank_transport().handler
    def handler(req):
        if req.url.path.endswith('/transactions'):
            page=int(req.url.params['page']);seen.append(page)
            return httpx.Response(200,json={'data':{'transaction':[{**TX,'transactionId':f'tx-{page}'}]},'meta':{'totalPages':2}})
        return original(req)
    data=asyncio.run(BankInABoxConnector(httpx.MockTransport(handler)).snapshot())
    assert seen==[1,2] and len(data[0]['transactions'])==2

def test_foreign_user_data_is_not_exposed(client):
    from backend.db import Session,ImportJob,Account,Notification
    with Session.begin() as db:
        db.add(ImportJob(id='other-job',user_id='another-user',filename='private.csv',path='/not-readable',account_id='manual-other'))
        db.add(Account(id='other-account',user_id='another-user',source_type='bank_in_a_box',name='Private account',currency='RUB',is_demo=True))
        db.add(Notification(id='other-note',user_id='another-user',scope='demo',kind='daily',title='Private',message='Private',dedupe_key='another-user:daily'))
    assert client.get('/api/imports/other-job').status_code==404
    assert client.patch('/api/notifications/other-note').status_code==404
    assert 'Private account' not in client.get('/api/connections').text
    assert 'Private' not in client.get('/api/notifications').text

def test_decimal_unknown_fields_are_serializable():
    from decimal import Decimal
    import json
    t=BankInABoxConnector().normalize_transaction({**TX,'unknown_numeric':Decimal('1.123456789')})
    assert json.loads(json.dumps(t.raw_payload))['unknown_numeric']=='1.123456789'
