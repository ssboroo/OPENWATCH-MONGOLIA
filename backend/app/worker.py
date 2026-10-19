import asyncio
import json
import time
from .collector import collect
from .pipeline import process_batch, heartbeat
from .db import Session
from .config import settings

async def pulse():
    while True:
        try:
            with Session() as db:
                heartbeat(db,'worker',{'status':'running'});db.commit()
        except Exception as exc:
            print(json.dumps({'service':'heartbeat','status':'failed','error':type(exc).__name__}),flush=True)
        await asyncio.sleep(30)

async def main():
    asyncio.create_task(pulse())
    if settings.catalog_bootstrap:
        from .discovery import supervisor
        asyncio.create_task(supervisor())
    last_collection=0
    while True:
        try:
            if time.monotonic()-last_collection>=max(60,settings.collection_interval):
                print(json.dumps({'service':'collector',**await collect()},ensure_ascii=False),flush=True)
                last_collection=time.monotonic()
            print(json.dumps({'service':'pipeline',**await process_batch()},ensure_ascii=False),flush=True)
            with Session() as db:
                heartbeat(db,'worker',{'status':'idle'});db.commit()
        except Exception as exc:
            print(json.dumps({'service':'worker','status':'failed','error':type(exc).__name__}),flush=True)
            try:
                with Session() as db:
                    heartbeat(db,'worker',{'status':'failed','error':type(exc).__name__});db.commit()
            except Exception:pass
        await asyncio.sleep(max(10,settings.worker_tick_seconds))

if __name__=='__main__':asyncio.run(main())
