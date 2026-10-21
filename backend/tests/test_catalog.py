from urllib.parse import urlsplit,parse_qs
import pytest
from sqlalchemy import select
from app.catalog import SITES, BY_DOMAIN, web_search_link, directory, domain_of
from app.models import Source
from app.collector import ingest
from test_archive import client, db, RSS, parse_feed

def test_catalog_has_500_unique_sites():
    assert len(SITES)==500 and len(BY_DOMAIN)==500
    assert all(s['website_url'].startswith('https://') and s['reference_url'].startswith('https://') for s in SITES)
    assert all('rank' not in s for s in SITES)

def test_web_search_does_not_fabricate_results(client):
    r=client.get('/api/v1/media/search',params={'q':'Оюутолгой ногдол ашиг'}).json()
    assert r['mode']=='external_search_links'
    assert r['total_sites']==500 and len(r['items'])==500 and len(r['groups'])==50
    assert len({d for g in r['groups'] for d in g['domains']})==500
    assert all(urlsplit(g['url']).hostname=='www.google.com' for g in r['groups'])
    assert 'results' not in r

def test_directory_pagination_and_filter(client):
    r=client.get('/api/v1/media?limit=20').json()
    assert len(r['items'])==20 and r['total']==500
    assert r['directory_media_total']==326 and r['directory_official_total']==174
    assert r['research_checked']==500
    assert r['items'][0]['archive_status']=='not_active'
    assert client.get('/api/v1/media?offset=500').json()['items']==[]
    assert client.get('/api/v1/media?q=ikon.mn').json()['total']==1
    assert client.get('/api/v1/media?availability=active').json()['total']==0
    assert client.get('/api/v1/media?limit=101').status_code==422
    assert client.get('/api/v1/media?category=untrusted').status_code==422

def test_single_domain_bing(client):
    r=client.get('/api/v1/media/search',params={'q':'Монгол & төсөв','domain':'ikon.mn','engine':'bing'}).json()
    assert r['total_sites']==1 and len(r['groups'])==1
    u=r['items'][0]['url']
    assert urlsplit(u).hostname=='www.bing.com'
    assert parse_qs(urlsplit(u).query)['q']==['(site:ikon.mn) Монгол & төсөв']

@pytest.mark.parametrize('path',['/api/v1/media/search?q=x&domain=localhost','/api/v1/media/search?q=%20','/api/v1/media/search?q=x&engine=evil','/api/v1/articles?domain=not-registered.test'])
def test_invalid_search_input(client,path):
    assert client.get(path).status_code==422

def test_archive_domain_filter(client,db):
    s=Source(name='iKon',endpoint='https://www.ikon.mn/rss',active=True)
    other=Source(name='GoGo',endpoint='https://gogo.mn/rss',active=False)
    db.add_all([s,other]);db.flush()
    rows=parse_feed(RSS)
    ingest(db,s,rows)
    rows[0]['url']='https://gogo.mn/second'
    ingest(db,other,rows);db.commit()
    r=client.get('/api/v1/articles?domain=ikon.mn&freshness=all').json()
    assert r['total']==1 and r['items'][0]['source_id']==s.id
    assert client.get('/api/v1/articles?domain=montsame.mn').json()['items']==[]
    row=client.get('/api/v1/media?q=ikon.mn').json()['items'][0]
    assert row['active_source_ids']==[s.id] and row['archive_status']=='active'

def test_domain_and_scope_validation():
    assert domain_of('https://www.ikon.mn/rss')=='ikon.mn'
    with pytest.raises(ValueError):web_search_link('x',['localhost'])
    with pytest.raises(ValueError):web_search_link('', ['ikon.mn'])

def test_imported_source_rights_update(client,db,monkeypatch):
    from app.config import settings
    from app.models import now
    monkeypatch.setattr(settings,'admin_token','x'*32)
    s=Source(name='Imported',endpoint='https://mnb.mn/rss.xml',validated_at=now())
    db.add(s);db.commit()
    r=client.patch(f'/api/v1/sources/{s.id}',json={'license':'Operator-confirmed terms URL','permission_note':'Operator-confirmed excerpt permission','active':True},headers={'Authorization':'Bearer '+'x'*32})
    assert r.status_code==200 and r.json()['active'] is True

def test_catalog_sync_validates_without_auto_activation(db,monkeypatch,capsys):
    import asyncio
    from sqlalchemy.orm import sessionmaker
    from app import catalog_sync
    factory=sessionmaker(db.bind,expire_on_commit=False)
    monkeypatch.setattr(catalog_sync,'Session',factory)
    async def fetch(url):return RSS
    async def no_wait(*args):pass
    monkeypatch.setattr(catalog_sync,'fetch_feed',fetch)
    monkeypatch.setattr(catalog_sync.asyncio,'sleep',no_wait)
    asyncio.run(catalog_sync.sync('mnb.mn'))
    asyncio.run(catalog_sync.sync('mnb.mn'))
    with factory() as session:
        rows=list(session.scalars(select(Source)))
        assert len(rows)==1 and rows[0].validated_at is not None
        assert rows[0].active is False and not rows[0].license

def test_directory_shows_live_feed_health_and_article_count(client,db):
    from app.models import now
    s=Source(name='Live RSS',endpoint='https://ikon.mn/rss',active=True,validated_at=now(),success_at=now())
    db.add(s);db.flush();ingest(db,s,parse_feed(RSS));db.commit()
    row=client.get('/api/v1/media?q=ikon.mn').json()['items'][0]
    assert row['feed_health']=='ready' and row['article_count']==1 and row['last_success_at']
    s.error='Timed out';db.commit()
    row=client.get('/api/v1/media?q=ikon.mn').json()['items'][0]
    assert row['feed_health']=='degraded' and row['article_count']==1
