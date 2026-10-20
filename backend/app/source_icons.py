"""Fixed-catalog publisher icons with bounded public-network fetches and process cache."""
import asyncio,time
from .catalog import BY_DOMAIN,probe_results,domain_of
from .security import fetch_feed

CACHE={}
INFLIGHT={}
LIMIT=asyncio.Semaphore(6)

def image_type(raw):
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png'
    if raw.startswith(b'\xff\xd8\xff'):return 'image/jpeg'
    if raw.startswith((b'GIF87a',b'GIF89a')):return 'image/gif'
    if raw.startswith(b'\x00\x00\x01\x00'):return 'image/x-icon'
    if raw.startswith(b'RIFF') and raw[8:12]==b'WEBP':return 'image/webp'
    return None

async def _read(domain):
    try:
        async with LIMIT:
            found=probe_results().get(domain,{}).get('icon_url')
            urls=[]
            if found and found.startswith('https://') and domain_of(found)==domain:urls.append(found)
            urls.append('https://'+domain+'/favicon.ico')
            for url in dict.fromkeys(urls):
                try:
                    raw=await asyncio.wait_for(fetch_feed(url),8)
                    mime=image_type(raw)
                    if mime and 0<len(raw)<=200000:
                        CACHE[domain]=(time.monotonic()+86400,raw,mime)
                        return raw,mime
                except Exception:continue
            CACHE[domain]=(time.monotonic()+3600,None,None)
            return None,None
    finally:INFLIGHT.pop(domain,None)

async def publisher_icon(domain):
    if domain not in BY_DOMAIN:return None,None
    cached=CACHE.get(domain)
    if cached and cached[0]>time.monotonic():return cached[1:]
    if domain not in INFLIGHT:INFLIGHT[domain]=asyncio.create_task(_read(domain))
    return await asyncio.shield(INFLIGHT[domain])
