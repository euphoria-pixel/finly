"""Compatibility bootstrap; fixes imports in an ephemeral copy, never upstream files."""
import os
from pathlib import Path
import shutil
import sys
import tempfile
source=Path(__file__).parent/'upstream'
runtime=Path(tempfile.mkdtemp(prefix='biab-runtime-'))
shutil.copytree(source,runtime,dirs_exist_ok=True)
for name in ('accounts','cards'):
    path=runtime/'api'/f'{name}.py'
    path.write_text(path.read_text().replace('from ..','from '))
path=runtime/'api'/'product_agreement_consents.py'
path.write_text('from services.auth_service import require_client\n'+path.read_text())
sys.path.insert(0,str(runtime))
os.chdir(runtime)
from main import app
from database import engine, AsyncSessionLocal
from models import Base, Client, Account, Transaction, Merchant
from sqlalchemy import select
from decimal import Decimal
from datetime import datetime, timedelta
import asyncio
async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        person=os.environ.get('BIAB_USERNAME','demo-student')
        if not await db.scalar(select(Client).where(Client.person_id==person)):
            client=Client(person_id=person,full_name='Синтетический студент',client_type='individual',segment='student')
            db.add(client); await db.flush()
            account=Account(client_id=client.id,account_number='40817810000000000001',account_type='checking',balance=Decimal('24750.00'),currency='RUB',status='active')
            saving=Account(client_id=client.id,account_number='40817810000000000002',account_type='savings',balance=Decimal('5000.00'),currency='RUB',status='active')
            merchant=Merchant(merchant_id='demo-campus',name='Кафе «Кампус»',mcc_code='5812',category='Кафе и доставка')
            db.add_all([account,saving,merchant]); await db.flush()
            today=datetime.utcnow().replace(hour=9,minute=0,second=0,microsecond=0)
            for ident,amount,direction,description,offset in [('stipend', '25000.00','credit','Стипендия',10),('cafe','250.00','debit','Обед в кампусе',1)]:
                db.add(Transaction(account_id=account.id,transaction_id='demo-'+ident,amount=Decimal(amount),direction=direction,currency='RUB',description=description,status='Booked',bank_transaction_code='01' if direction=='debit' else '03',merchant_id=merchant.id if direction=='debit' else None,transaction_date=today-timedelta(days=offset)))
            db.add(Transaction(account_id=saving.id,transaction_id='demo-savings',amount=Decimal('5000.00'),direction='credit',currency='RUB',description='Подработка',status='Booked',transaction_date=today-timedelta(days=10)))
            await db.commit()
    await engine.dispose()
asyncio.run(seed())
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=8000)
