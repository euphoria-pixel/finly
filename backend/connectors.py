from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
import csv
import io
import json
import os
import ssl
from pathlib import Path
import hashlib
from collections import Counter
import httpx
from pydantic import BaseModel, Field
from .schemas import TransactionInput, money_minor

class ConnectorError(Exception):
    pass

class BankConnector(ABC):
    @abstractmethod
    async def test_connection(self): ...
    @abstractmethod
    async def list_accounts(self): ...
    @abstractmethod
    async def fetch_transactions(self, account_id, from_date, to_date, cursor=None): ...
    @abstractmethod
    def normalize_transaction(self, raw): ...
    def get_sync_status(self):
        return {'events_supported': False, 'mode': 'pull'}

class StatementParser(ABC):
    @abstractmethod
    def parse(self, text): ...

class CSVStatementParser(StatementParser):
    def parse(self, text):
        text = text.lstrip('\ufeff')
        delimiter = ';' if text.splitlines()[0].count(';') > text.splitlines()[0].count(',') else ','
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        required = {'дата','описание','сумма','валюта'}
        if not reader.fieldnames or not required.issubset({x.strip().lower() for x in reader.fieldnames}):
            raise ValueError('CSV: нужны колонки дата, описание, сумма, валюта; категория — необязательна.')
        rows = []
        for row in reader:
            row = {str(k).strip().lower():v for k,v in row.items() if k is not None}
            item = {'date': row.get('дата',''), 'description':row.get('описание',''),
                'amount':row.get('сумма',''), 'currency':row.get('валюта',''),
                'category':row.get('категория') or 'Другое', 'include':True}
            try:
                ManualStatementConnector().normalize_transaction(item)
                item['error'] = None
            except (ValueError, TypeError):
                item['error'] = 'Проверьте дату, сумму и валюту; исправьте или исключите строку.'
            rows.append(item)
            if len(rows) > 5000:
                raise ValueError('Максимум 5000 операций в одном импорте.')
        if not rows:
            raise ValueError('В CSV нет операций.')
        return rows

class ManualStatementConnector(BankConnector):
    async def test_connection(self): return {'ok': True}
    async def list_accounts(self): return []
    async def fetch_transactions(self, account_id, from_date, to_date, cursor=None): return []
    def normalize_transaction(self, raw):
        value = raw['date'].strip()
        try:
            dt = datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:
            dt = datetime.strptime(value, '%d.%m.%Y')
        currency = raw['currency'].strip().upper().replace('₽','RUB')
        amount = money_minor(raw['amount'], currency)
        direction = raw.get('direction') or ('income' if amount > 0 else 'expense')
        desc = raw['description']
        if not raw.get('direction') and any(x in desc.lower() for x in ('между своими', 'перевод себе', 'собственных средств')):
            direction = 'transfer'
        key = hashlib.sha256(json.dumps([dt.isoformat(),desc,amount,currency],ensure_ascii=False).encode()).hexdigest()
        return TransactionInput(external_id=key, account_id=raw.get('account_id','manual-demo'),
            source_type='manual_import', source_name='Выписка', occurred_at=dt,
            amount_minor=amount,currency=currency,direction=direction,description=desc,
            bank_category=raw.get('category') or 'Другое',status='posted',
            is_demo=raw.get('is_demo',True),raw_payload=raw)
    def normalize_rows(self, rows, account_id='manual-demo', is_demo=True):
        counts = Counter()
        result = []
        for row in rows:
            if not row.get('include', True): continue
            row = {k:v for k,v in row.items() if k != 'error'}
            t = self.normalize_transaction({**row, 'account_id':account_id,'is_demo':is_demo})
            counts[t.external_id] += 1
            t.external_id += ':' + str(counts[t.external_id])
            result.append(t)
        return result

