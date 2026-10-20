import time
from collections import deque
from test_archive import client
from app.main import buckets


def test_icon_budget_does_not_block_articles_or_health(client,monkeypatch):
    from app import source_icons
    async def icon(domain):return b'\x89PNG\r\n\x1a\nfixture','image/png'
    monkeypatch.setattr(source_icons,'publisher_icon',icon)
    buckets[('testclient','icons')]=deque([time.monotonic()]*600)
    r=client.get('/api/v1/source-icons/ikon.mn')
    assert r.status_code==429 and r.headers['x-ratelimit-scope']=='icons'
    assert client.get('/api/v1/statistics').status_code==200
    assert client.get('/api/v1/articles').status_code==200
    buckets[('testclient','api')]=deque([time.monotonic()]*120)
    assert client.get('/api/v1/articles').status_code==429
    assert client.get('/health').status_code==200


def test_exhausted_api_budget_does_not_break_cached_logos(client,monkeypatch):
    from app import source_icons
    async def icon(domain):return b'\x89PNG\r\n\x1a\nfixture','image/png'
    monkeypatch.setattr(source_icons,'publisher_icon',icon)
    buckets[('testclient','api')]=deque([time.monotonic()]*120)
    r=client.get('/api/v1/articles')
    assert r.status_code==429 and 1<=int(r.headers['retry-after'])<=60
    assert r.headers['x-ratelimit-scope']=='api'
    assert client.get('/api/v1/source-icons/ikon.mn').status_code==200
