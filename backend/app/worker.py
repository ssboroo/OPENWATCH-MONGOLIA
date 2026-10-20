import asyncio
import json
from .collector import collect
from .pipeline import process_batch, heartbeat
from .db import Session
from .config import settings
from .ai import Ollama

async def pulse():
    while True:
        try:
            with Session() as db:
                heartbeat(db,'worker',{'status':'running'});db.commit()
        except Exception as exc:print(json.dumps({'service':'heartbeat','status':'failed','error':type(exc).__name__}),flush=True)
        await asyncio.sleep(30)

async def collection_loop():
    while True:
        try:print(json.dumps({'service':'collector',**await collect()},ensure_ascii=False),flush=True)
        except Exception as exc:print(json.dumps({'service':'collector','status':'failed','error':type(exc).__name__}),flush=True)
        await asyncio.sleep(max(60,settings.collection_interval))

async def analysis_loop():
    while True:
        try:
            ready=not settings.ai_enabled or await Ollama().models_ready()
            with Session() as db:
                heartbeat(db,'ai_models',{'status':'installed' if ready and settings.ai_enabled else 'waiting_for_models' if settings.ai_enabled else 'disabled','enabled':settings.ai_enabled});db.commit()
            if ready:print(json.dumps({'service':'pipeline',**await process_batch()},ensure_ascii=False),flush=True)
        except Exception as exc:
            print(json.dumps({'service':'pipeline','status':'failed','error':type(exc).__name__}),flush=True)
            try:
                with Session() as db:
                    heartbeat(db,'pipeline',{'status':'failed','error':type(exc).__name__});db.commit()
            except Exception:pass
        await asyncio.sleep(max(10,settings.worker_tick_seconds))

async def main():
    tasks=[pulse(),collection_loop(),analysis_loop()]
    if settings.catalog_bootstrap:
        from .discovery import supervisor
        tasks.append(supervisor())
    await asyncio.gather(*tasks)

if __name__=='__main__':asyncio.run(main())
