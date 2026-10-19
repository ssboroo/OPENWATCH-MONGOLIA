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
