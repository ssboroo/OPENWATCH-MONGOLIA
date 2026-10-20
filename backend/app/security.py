import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlsplit, urljoin, parse_qsl
from urllib.robotparser import RobotFileParser
import httpx
from .config import settings
from .catalog import BY_DOMAIN

async def resolve_public(url):
    u = urlsplit(url)
    allowed = {h.strip().lower() for h in settings.allowed_hosts.split(',') if h.strip()}
    allowed |= {host for domain in BY_DOMAIN for host in (domain, 'www.'+domain)}
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443) or not u.hostname or u.hostname.lower() not in allowed:
        raise ValueError('HTTPS URL must use an explicitly allowed hostname')
    if any(key.casefold() in {'api_key','apikey','access_token','password','secret','authorization','token','signature'} for key,_ in parse_qsl(u.query)):
        raise ValueError('Credentials are not allowed in public source URLs')
    addresses = await asyncio.get_running_loop().getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
    ips = {a[4][0] for a in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('Private/reserved destination blocked')
    return u, sorted(ips)[0]

_last_fetch = {}
_host_locks = {}

async def wait_for_host(url, delay):
    if not delay:return
    host=urlsplit(url).hostname
    lock=_host_locks.setdefault(host,asyncio.Lock())
    async with lock:
        remaining=delay-(time.monotonic()-_last_fetch.get(host,0))
        if remaining>0:await asyncio.sleep(remaining)
        _last_fetch[host]=time.monotonic()

async def _download(url, redirects=3, check_robots=False, crawl_delay=0):
    await wait_for_host(url,crawl_delay)
    # Pin the resolved address and retain hostname for TLS SNI and certificate validation.
    # trust_env=False prevents unvalidated proxy routing.
    u, ip = await resolve_public(url)
    authority = f'[{ip}]' if ':' in ip else ip
    pinned = f'https://{authority}{u.path or "/"}' + (f'?{u.query}' if u.query else '')
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        async with client.stream('GET', pinned, headers={'Host': u.hostname, 'User-Agent': 'OpenWatch/1.0 (+public-feed-archive)'}, extensions={'sni_hostname': u.hostname}) as r:
            if r.is_redirect:
                if redirects <= 0:
                    raise ValueError('Too many redirects')
                target=urljoin(url,r.headers['location'])
                return await fetch_feed(target,redirects-1) if check_robots else await download(target,redirects-1)
            r.raise_for_status()
            data = bytearray()
            async for chunk in r.aiter_bytes():
                data.extend(chunk)
                if len(data) > settings.max_feed_bytes:
                    raise ValueError('Response exceeds size limit')
            return bytes(data)

_robots_cache = {}
_policy_locks = {}
ROBOTS_TTL = 300

async def robots_policy(host):
    cached=_robots_cache.get(host)
    if cached and cached[0]>time.monotonic():return cached[1]
    lock=_policy_locks.setdefault(host,asyncio.Lock())
    async with lock:
        cached=_robots_cache.get(host)
        if cached and cached[0]>time.monotonic():return cached[1]
        try:raw=await download(f'https://{host}/robots.txt')
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code!=404:raise ValueError('Unable to verify robots policy') from exc
            raw=b''
        policy=RobotFileParser()
        policy.parse(raw.decode('utf-8',errors='replace').splitlines())
        if len(_robots_cache)>=512:_robots_cache.pop(next(iter(_robots_cache)))
        _robots_cache[host]=(time.monotonic()+ROBOTS_TTL,policy)
        return policy

async def fetch_feed(url, redirects=3):
    u, _ = await resolve_public(url)
    policy = await robots_policy(u.hostname)
    if not policy.can_fetch('OpenWatch', url):
        raise ValueError('robots.txt disallows collection')
    if (policy.crawl_delay('OpenWatch') or 0) > settings.collection_interval:
        raise ValueError('Collection interval violates robots crawl-delay')
    delay=float(policy.crawl_delay('OpenWatch') or 0)
    rate=policy.request_rate('OpenWatch')
    if rate and rate.requests>0:delay=max(delay,rate.seconds/rate.requests)
    if delay>settings.collection_interval:raise ValueError('Collection interval violates robots request-rate')
    return await download(url,redirects,check_robots=True,crawl_delay=max(1,delay))

async def download(url, redirects=3, check_robots=False, crawl_delay=0):
    for attempt in range(3):
        try:
            return await _download(url, redirects, check_robots, crawl_delay)
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)
