import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urljoin
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
    addresses = await asyncio.get_running_loop().getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
    ips = {a[4][0] for a in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('Private/reserved destination blocked')
    return u, sorted(ips)[0]

async def _download(url, redirects=3):
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
                return await download(urljoin(url, r.headers['location']), redirects - 1)
            r.raise_for_status()
            data = bytearray()
            async for chunk in r.aiter_bytes():
                data.extend(chunk)
                if len(data) > settings.max_feed_bytes:
                    raise ValueError('Response exceeds size limit')
            return bytes(data)

async def fetch_feed(url):
    u, _ = await resolve_public(url)
    robots_url = f'https://{u.hostname}/robots.txt'
    try:
        raw = await download(robots_url)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise ValueError('Unable to verify robots policy') from exc
        raw = b''
    policy = RobotFileParser()
    policy.parse(raw.decode('utf-8', errors='replace').splitlines())
    if not policy.can_fetch('OpenWatch', url):
        raise ValueError('robots.txt disallows collection')
    if (policy.crawl_delay('OpenWatch') or 0) > settings.collection_interval:
        raise ValueError('Collection interval violates robots crawl-delay')
    return await download(url)

async def download(url, redirects=3):
    for attempt in range(3):
        try:
            return await _download(url, redirects)
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)
