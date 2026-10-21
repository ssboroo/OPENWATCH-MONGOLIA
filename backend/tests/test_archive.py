import os
os.environ['DATABASE_URL'] = 'sqlite://'
import asyncio
from datetime import timezone
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.models import Base, Source, Article, ArticleVersion, Event
from app.collector import canonical, parse_feed, ingest, rebuild_events, similarity, digest
from app.main import app, buckets
from app.db import get_db
from app.config import settings
from app.security import resolve_public

RSS = b'''<rss version="2.0"><channel><title>Test</title><link>https://news.example/</link><description>Test</description><item><title>Budget report</title><link>https://news.example/one?utm_source=test</link><description>Public budget 2026</description><pubDate>Mon, 19 Oct 2026 10:00:00 +0800</pubDate></item></channel></rss>'''
@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine) # Tests only: production uses Alembic.
    with Session(engine, expire_on_commit=False) as s:
        yield s
    engine.dispose()

@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    buckets.clear()
    from app.main import submission_buckets
    submission_buckets.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_rss_timestamp():
    rows = parse_feed(RSS)
    assert rows[0]['published_at'].hour == 2
    assert rows[0]['published_at'].tzinfo == timezone.utc
    assert rows[0]['url'] == 'https://news.example/one'

def test_atom():
    raw=b'<feed xmlns="http://www.w3.org/2005/Atom"><title>T</title><id>x</id><updated>2026-10-19T02:00:00Z</updated><entry><title>A</title><id>a</id><link href="https://news.example/a"/><updated>2026-10-19T02:00:00Z</updated></entry></feed>'
    assert parse_feed(raw)[0]['updated_at'].hour == 2

@pytest.mark.parametrize('raw',[b'not xml',b'<html>not a feed</html>',b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss>&x;</rss>'])
def test_invalid_rss(raw):
    with pytest.raises(Exception): parse_feed(raw)

def test_url_normalization():
    assert canonical('https://EXAMPLE.com/x?b=2&utm_source=t&a=1#frag') == 'https://example.com/x?a=1&b=2'
    with pytest.raises(ValueError): canonical('javascript:alert(1)')

def test_hash_and_near():
    assert digest('a','b') == digest('a','b')
    assert digest('a','b') != digest('a','c')
    assert similarity('Монгол улсын шинэ төсөв батлагдлаа','Шинэ төсөв Монгол улсын батлагдлаа') == 1
    assert similarity('Монгол төсөв','rain storm') == 0

def test_archive_versions_and_cluster(db):
    s=Source(name='Test',endpoint='https://news.example/rss');db.add(s);db.flush()
    rows=parse_feed(RSS)
    assert ingest(db,s,rows)==1
    assert ingest(db,s,rows)==0
    assert db.scalar(select(func.count()).select_from(ArticleVersion))==1
    rows[0]['title']='Updated public budget'
    ingest(db,s,rows)
    assert db.scalar(select(Article)).version==2
    assert db.scalar(select(func.count()).select_from(ArticleVersion))==2
    rows[0]['url']='https://news.example/two'
    ingest(db,s,rows);rebuild_events(db);db.commit()
    assert db.scalar(select(func.count()).select_from(Event))==1
    assert db.scalar(select(Article)).first_seen_at != db.scalar(select(Article)).published_at

def test_empty_api_and_auth(client):
    assert client.get('/api/v1/statistics').json()=={'sources':0,'articles':0,'events':0,'matches':0}
    assert client.get('/api/v1/articles').json()['items']==[]
    assert client.get('/api/v1/articles/999').status_code==404
    assert client.get('/api/v1/articles?limit=101').status_code==422
    assert client.post('/api/v1/collect/run').status_code==401
    assert client.get('/health').json()['ai']=='not_enabled'

def test_pagination_and_links(client,db):
    s=Source(name='Test',endpoint='https://news.example/rss');db.add(s);db.flush()
    ingest(db,s,parse_feed(RSS));db.commit()
    r=client.get('/api/v1/articles?limit=1&freshness=all').json()
    assert r['total']==1 and r['items'][0]['url']=='https://news.example/one'
    assert client.get('/api/v1/articles?offset=1').json()['items']==[]
    assert client.get('/api/v1/search?q=Budget&freshness=all').json()['total']==1
    assert client.get('/api/v1/search?q=%25').json()['total']==0

def test_rate_limit(client):
    for _ in range(120): assert client.get('/api/v1/reports').status_code==200
    assert client.get('/api/v1/reports').status_code==429

def test_ssrf(monkeypatch):
    monkeypatch.setattr(settings,'allowed_hosts','127.0.0.1,localhost')
    for url in ['https://127.0.0.1/','https://localhost/','http://localhost/','https://other.example/']:
        with pytest.raises(ValueError): asyncio.run(resolve_public(url))

def test_database_failure(client,monkeypatch,db):
    from sqlalchemy.exc import OperationalError
    def fail(*args,**kwargs): raise OperationalError('SELECT',{},Exception('offline'))
    monkeypatch.setattr(db,'execute',fail)
    assert client.get('/health').status_code==503

def test_activation_requires_validation(client,db,monkeypatch):
    monkeypatch.setattr(settings,'admin_token','x'*32)
    s=Source(name='T',endpoint='https://news.example/rss');db.add(s);db.commit()
    assert client.patch(f'/api/v1/sources/{s.id}',json={'active':True},headers={'Authorization':'Bearer '+'x'*32}).status_code==422

def test_feed_timestamp_without_timezone_is_not_invented():
    raw=RSS.replace(b'Mon, 19 Oct 2026 10:00:00 +0800',b'Mon, 19 Oct 2026 10:00:00')
    result=parse_feed(raw)[0]
    assert result['published_at'] is None
    assert result['source_metadata']['published_raw']=='Mon, 19 Oct 2026 10:00:00'

def test_non_ascii_auth_header_is_rejected_without_server_error(client,monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings,'admin_token','x'*32)
    response=client.post('/api/v1/collect/run',headers=[(b'authorization',b'Bearer \xff')])
    assert response.status_code==401
