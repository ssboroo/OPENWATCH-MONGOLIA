import asyncio
import socket
import pytest
from app import security
from app.config import settings

def test_dns_rebinding_rejected(monkeypatch):
    monkeypatch.setattr(settings,'allowed_hosts','news.example')
    class Loop:
        async def getaddrinfo(self,*args,**kwargs):
            return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))]
    monkeypatch.setattr(security.asyncio,'get_running_loop',lambda:Loop())
    with pytest.raises(ValueError,match='Private'):
        asyncio.run(security.resolve_public('https://news.example/rss'))

def test_robots_denied(monkeypatch):
    async def resolve(url): return None,None
    async def download(url): return b'User-agent: *\nDisallow: /rss\n'
    monkeypatch.setattr(security,'resolve_public',resolve)
    monkeypatch.setattr(security,'download',download)
    # Return an actual parsed URL for the robots check.
    from urllib.parse import urlsplit
    async def resolve(url): return urlsplit(url),'93.184.216.34'
    monkeypatch.setattr(security,'resolve_public',resolve)
    with pytest.raises(ValueError,match='robots'):
        asyncio.run(security.fetch_feed('https://news.example/rss'))

def test_collector_integration_and_failure(db, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, func
    from app import collector
    from app.models import Source, Article, CollectionRun
    from test_archive import RSS
    factory=sessionmaker(db.bind,expire_on_commit=False)
    monkeypatch.setattr(collector,'Session',factory)
    with factory() as s:
        s.add(Source(name='Test',endpoint='https://news.example/rss',active=True));s.commit()
    async def feed(url): return RSS
    monkeypatch.setattr(collector,'fetch_feed',feed)
    result=asyncio.run(collector.collect())
    assert result['status']=='completed' and result['added']==1
    async def offline(url): raise TimeoutError('feed timeout')
    monkeypatch.setattr(collector,'fetch_feed',offline)
    result=asyncio.run(collector.collect())
    assert result['status']=='partial' and result['errors']
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Article))==1
        assert s.scalar(select(CollectionRun).order_by(CollectionRun.id.desc())).finished_at

def test_credentials_in_public_source_and_article_urls_are_blocked_before_dns():
    from app.collector import canonical
    with pytest.raises(ValueError,match='Credentials'):
        asyncio.run(security.resolve_public('https://ikon.mn/rss?api_key=not-a-real-secret'))
    with pytest.raises(ValueError,match='Credential'):
        canonical('https://ikon.mn/article?access_token=not-a-real-secret')

def test_redirect_rechecks_robots_and_pins_host_sni(monkeypatch):
    import httpx
    from urllib.parse import urlsplit
    original=httpx.AsyncClient;calls=[]
    async def public(url):return urlsplit(url),'93.184.216.34'
    def handler(request):
        host=request.headers['host'];calls.append((host,request.url.path))
        assert request.url.host=='93.184.216.34' and request.extensions['sni_hostname']==host
        if request.url.path=='/robots.txt':
            return httpx.Response(200,text='User-agent: *\nDisallow: /feed\n' if host=='gogo.mn' else 'User-agent: *\nAllow: /\n')
        return httpx.Response(302,headers={'Location':'https://gogo.mn/feed'})
    def client(**kwargs):return original(transport=httpx.MockTransport(handler),**kwargs)
    monkeypatch.setattr(security,'resolve_public',public)
    monkeypatch.setattr(security.httpx,'AsyncClient',client)
    security._last_fetch.clear()
    with pytest.raises(ValueError,match='robots'):
        asyncio.run(security.fetch_feed('https://ikon.mn/feed'))
    assert ('gogo.mn','/robots.txt') in calls and ('gogo.mn','/feed') not in calls


def test_robots_cache_shares_fetch_and_expires_without_bypassing_denial(monkeypatch):
    from urllib.parse import urlsplit
    clock=[0];calls=[]
    monkeypatch.setattr(security,'_robots_cache',{})
    monkeypatch.setattr(security,'_policy_locks',{})
    monkeypatch.setattr(security.time,'monotonic',lambda:clock[0])
    async def resolve(url):return urlsplit(url),'93.184.216.34'
    async def download(url,*args,**kwargs):
        calls.append(url)
        if url.endswith('/robots.txt'):
            await asyncio.sleep(0)
            return b'User-agent: *\nAllow: /\n' if clock[0]<300 else b'User-agent: *\nDisallow: /\n'
        return b'public content'
    monkeypatch.setattr(security,'resolve_public',resolve);monkeypatch.setattr(security,'download',download)
    async def first():return await asyncio.gather(security.fetch_feed('https://cache.example/one'),security.fetch_feed('https://cache.example/two'))
    assert asyncio.run(first())==[b'public content',b'public content']
    assert calls.count('https://cache.example/robots.txt')==1
    clock[0]=301
    with pytest.raises(ValueError,match='robots'):asyncio.run(security.fetch_feed('https://cache.example/three'))
    assert 'https://cache.example/three' not in calls
