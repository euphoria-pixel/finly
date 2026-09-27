"""Read-only local Bank-in-a-Box adapter. Contract: pinned api/auth.py, accounts.py."""
import json
import os
from decimal import Decimal
from urllib.parse import urlparse
import httpx
from .connectors import BankConnector, ConnectorError
from .schemas import TransactionInput, money_minor

class BankInABoxConnector(BankConnector):
    def __init__(self, transport=None):
        self.base_url=os.getenv('BIAB_BASE_URL','http://127.0.0.1:8080').rstrip('/')
        url=urlparse(self.base_url)
        if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or url.username or url.password:
            raise ConnectorError('Учебный банк должен находиться на локальном HTTP-адресе.')
        self.transport=transport
        self.token=None
        self.account_ids=set()

    async def request(self,method,path,**kwargs):
        try:
            async with httpx.AsyncClient(base_url=self.base_url,timeout=12,transport=self.transport,trust_env=False) as client:
                response=await client.request(method,path,headers={'Authorization':'Bearer '+self.token} if self.token else {},**kwargs)
                response.raise_for_status()
                return json.loads(response.text,parse_float=Decimal)
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f'Учебный банк вернул HTTP {exc.response.status_code}. Проверьте локальный запуск и тестовую учётную запись.') from exc
        except (httpx.RequestError,ValueError) as exc:
            raise ConnectorError('Учебный банк недоступен или вернул некорректный JSON. Сохранённая история доступна.') from exc

    async def authenticate(self):
        password=os.getenv('BIAB_PASSWORD')
        if not password:raise ConnectorError('Задайте BIAB_PASSWORD в backend .env.')
        data=await self.request('POST','/auth/login',json={'username':os.getenv('BIAB_USERNAME','demo-student'),'password':password})
        if not isinstance(data.get('access_token'),str):raise ConnectorError('В ответе авторизации нет токена.')
        self.token=data['access_token']

    async def list_accounts(self):
        if not self.token:await self.authenticate()
        data=await self.request('GET','/accounts')
        try:
            accounts=data['data']['account']
            self.account_ids={a['accountId'] for a in accounts}
            if not all(isinstance(i,str) and i.startswith('acc-') and i[4:].isdigit() for i in self.account_ids):raise ValueError()
            return accounts
        except (KeyError,TypeError,ValueError) as exc:raise ConnectorError('Неверная структура списка счетов.') from exc

    def check_account(self,account_id):
        # Upstream detail routes do not consistently verify ownership. Only use IDs from /accounts.
        if account_id not in self.account_ids:raise ConnectorError('Счёт не принадлежит авторизованному тестовому клиенту.')

    async def get_balances(self,account_id):
        self.check_account(account_id)
        data=await self.request('GET',f'/accounts/{account_id}/balances')
        try:
            balance=next(b for b in data['data']['balance'] if b['type']=='InterimBooked')
            if balance['accountId']!=account_id:raise ValueError()
            return balance
        except (KeyError,TypeError,StopIteration,ValueError) as exc:raise ConnectorError('В ответе нет согласованного проведённого баланса.') from exc

    async def fetch_transactions(self,account_id,from_date=None,to_date=None,cursor=None):
        self.check_account(account_id)
        # Date parameters are TODO upstream; always revisit history to detect status changes.
        return await self.request('GET',f'/accounts/{account_id}/transactions',params={'page':int(cursor or 1),'limit':100})

    async def snapshot(self):
        accounts=await self.list_accounts()
        snapshots=[]
        for account in accounts:
            ident=account['accountId']; rows=[]
            for page in range(1,101):
                data=await self.fetch_transactions(ident,cursor=page)
                try:
                    batch=data['data']['transaction']
                    if not isinstance(batch,list) or any(t['accountId']!=ident for t in batch):raise ValueError()
                    rows.extend(batch)
                    pages=int(data['meta']['totalPages'])
                    if pages<0 or pages>100:raise ValueError()
                    if page>=pages:break
                except (KeyError,TypeError,ValueError) as exc:raise ConnectorError('Неполная или неверная история банка; синхронизация отменена.') from exc
            else:raise ConnectorError('История превышает лимит 100 страниц; синхронизация отменена.')
            if 'totalRecords' in data.get('meta',{}) and len(rows)!=int(data['meta']['totalRecords']):
                raise ConnectorError('История изменилась во время чтения или получена не полностью; повторите синхронизацию.')
            balance=await self.get_balances(ident)
            snapshots.append({'account':account,'balance':balance,'transactions':rows})
        return snapshots

    async def test_connection(self):
        accounts=await self.list_accounts()
        return {'ok':True,'message':f'Учебный банк доступен, счетов: {len(accounts)}'}

    def normalize_transaction(self,raw):
        try:
            raw=json.loads(json.dumps(raw,default=str))
            currency=raw['amount']['currency'];amount=abs(money_minor(raw['amount']['amount'],currency))
            indicator=raw['creditDebitIndicator']
            if indicator not in ('Credit','Debit'):raise ValueError()
            amount*=1 if indicator=='Credit' else -1
            status={'booked':'posted','completed':'posted','pending':'pending','declined':'reversed','reversed':'reversed','cancelled':'reversed','refunded':'reversed'}.get(str(raw.get('status','')).lower(),'unknown')
            code=(raw.get('bankTransactionCode') or {}).get('code','')
            desc=raw.get('transactionInformation') or ''
            direction='income' if amount>=0 else 'expense'
            # Generic IssuedDebitTransfer does NOT prove a transfer between own accounts.
            if code in ('InternalTransfer','OwnAccountTransfer') or 'между своими' in desc.lower():direction='transfer'
            if amount>0 and (code in ('Refund','CardRefund') or 'возврат' in desc.lower()):direction='expense'
            merchant=raw.get('merchant') or {}
            return TransactionInput(external_id=raw['transactionId'],account_id='biab:'+raw['accountId'],source_type='bank_in_a_box',source_name='Кампус · Bank-in-a-Box',occurred_at=raw['bookingDateTime'],posted_at=raw['bookingDateTime'] if status=='posted' else None,amount_minor=amount,currency=currency,direction=direction,description=desc,merchant_name=merchant.get('name'),mcc=merchant.get('mccCode'),bank_category=merchant.get('category') or ('Доход' if direction=='income' else 'Другое'),status=status,is_demo=True,raw_payload=raw)
        except (KeyError,TypeError,ValueError) as exc:raise ConnectorError('Не удалось нормализовать операцию Bank-in-a-Box.') from exc
