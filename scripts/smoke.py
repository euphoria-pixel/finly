"""Live HTTP smoke test against the running application and local bank.
Use only the synthetic demo profile; imported statements are preserved.
Run: .venv/bin/python -m scripts.smoke [--llm]
"""
import argparse
import asyncio
import json
from pathlib import Path
import httpx

async def run(use_llm=False):
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=150) as client:
        async def call(method,path,**kwargs):
            r=await client.request(method,'/api'+path,**kwargs);r.raise_for_status();return r.json()
        await call('POST','/plan?enabled=false')
        content=Path('fixtures/demo-statement.csv').read_bytes()
        job=await call('POST','/imports',files={'file':('demo.csv',content,'text/csv')})
        assert job['status']=='preview'
        rows=[{k:v for k,v in row.items() if k!='error'} for row in job['rows']]
        imported=await call('POST',f"/imports/{job['id']}/confirm",json={'rows':rows})
        print('CSV confirmed:',imported,flush=True)
        if use_llm:
            job=await call('POST','/imports',files={'file':('demo.pdf',Path('fixtures/demo-statement.pdf').read_bytes(),'application/pdf')})
            assert job['status']=='awaiting_approval'
            # Fixture is generated entirely from synthetic descriptions/amounts.
            await call('POST',f"/imports/{job['id']}/process",json={'approved':True})
            for _ in range(100):
                await asyncio.sleep(2)
                job=await call('GET',f"/imports/{job['id']}")
                if job['status']!='processing':break
            print('Live PDF/LLM:',job['status'],'rows:',len(job['rows']),flush=True)
            assert job['status']=='preview',job.get('error')
            rows=[{k:v for k,v in row.items() if k!='error'} for row in job['rows']]
            await call('POST',f"/imports/{job['id']}/confirm",json={'rows':rows})
        await call('POST','/plan?enabled=true')
        synced=await call('POST','/connections/bank-in-a-box/sync')
        print('Bank real HTTP:',synced,flush=True)
        bank=await call('GET','/dashboard?scope=bank')
        assert len(bank['accounts'])==2 and bank['balance_minor']==2975000
        assert bank['transaction_count']==3
        repeat=await call('POST','/connections/bank-in-a-box/sync')
        assert repeat['created']==0 and repeat['duplicates']==3
        await call('POST','/demo/reset')
        before=await call('GET','/dashboard')
        current=await call('GET','/events/latest?tail=true')
        cursor=max((e['id'] for e in current),default=0)
        received=[];ready=asyncio.Event()
        async def listen():
            async with client.stream('GET','/api/events',headers={'Last-Event-ID':str(cursor)}) as stream:
                stream.raise_for_status();ready.set()
                async for line in stream.aiter_lines():
                    if line.startswith('data: '):
                        event=json.loads(line[6:]);received.append(event['type'])
                        if {'transaction.created','budget.updated','notification.created'}.issubset(received):return
        task=asyncio.create_task(listen())
        await ready.wait()
        await call('POST','/simulator/transactions',json={'amount_minor':1200000,'merchant':'Smoke: синтетический ноутбук','category':'Покупки'})
        await asyncio.wait_for(task,10)
        after=await call('GET','/dashboard')
        assert after['balance_minor']==before['balance_minor']-1200000
        assert after['daily_limit_minor']<before['daily_limit_minor']
        assert (await call('GET','/dashboard?scope=bank'))['balance_minor']==bank['balance_minor']
        answer=await call('POST','/assistant/chat',json={'message':'Хватит ли денег до стипендии?','use_llm':use_llm})
        print('SSE:',sorted(set(received)),flush=True)
        print('Budget:',before['balance_minor'],'→',after['balance_minor'],'daily:',before['daily_limit_minor'],'→',after['daily_limit_minor'],flush=True)
        print('Assistant:',answer,flush=True)
        await call('POST','/plan?enabled=false')
        assert (await call('GET','/dashboard?scope=bank'))['transaction_count']==3
        await call('POST','/plan?enabled=true')
        await call('POST','/connections/bank-in-a-box/polling?enabled=true')
        prior=(await call('GET','/dashboard?scope=bank'))['last_bank_sync']
        for _ in range(25):
            await asyncio.sleep(1)
            updated=(await call('GET','/dashboard?scope=bank'))['last_bank_sync']
            if updated!=prior:break
        else:raise AssertionError('Automatic bank polling did not run')
        print('Automatic polling:',prior,'→',updated,flush=True)
        print('LIVE SMOKE PASSED',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--llm',action='store_true')
    asyncio.run(run(parser.parse_args().llm))
