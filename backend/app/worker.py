import asyncio
import json
from .collector import collect
from .config import settings
async def main():
    while True:
        try:
            print(json.dumps(await collect(), ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({'status':'failed','error':str(exc)[:400]}), flush=True)
        await asyncio.sleep(max(60, settings.collection_interval))
if __name__ == '__main__':
    asyncio.run(main())
