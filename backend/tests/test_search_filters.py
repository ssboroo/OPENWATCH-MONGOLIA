from datetime import datetime, timezone
from app.models import Source, Article
from test_archive import client, db

def seed(db):
    sources=[Source(name='iKon',endpoint='https://ikon.mn/rss'),Source(name='GoGo',endpoint='https://gogo.mn/rss')]
    db.add_all(sources);db.flush()
    stamps=['2026-10-18T15:59:59','2026-10-18T16:00:00','2026-10-19T15:59:59','2026-10-19T16:00:00',None]
    for i,stamp in enumerate(stamps):
        db.add(Article(source_id=sources[i%2].id,url=f'https://ikon.mn/test/{i}',title='Budget 100% '+str(i),excerpt='Archive evidence',text_hash=str(i)*64,published_at=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc) if stamp else None,first_seen_at=datetime(2026,10,20,i,tzinfo=timezone.utc)))
    db.commit()

def test_inclusive_mongolian_day_and_unknown_date(client,db):
    seed(db)
    r=client.get('/api/v1/articles?date_from=2026-10-19&date_to=2026-10-19').json()
    assert r['total']==2 and {a['title'] for a in r['items']}=={'Budget 100% 1','Budget 100% 2'}
    assert r['timezone']=='Asia/Ulaanbaatar'
    assert client.get('/api/v1/articles?date_from=2026-10-20&date_to=2026-10-19').status_code==422
    assert client.get('/api/v1/articles?date_from=invalid').status_code==422
    assert client.get('/api/v1/articles?date_to=9999-12-31').status_code==422

def test_combined_scope_sort_and_literal_wildcards(client,db):
    seed(db)
    r=client.get('/api/v1/articles',params={'q':'100%','domain':'ikon.mn','date_from':'2026-10-19','date_to':'2026-10-19','category':'news'}).json()
    assert r['total']==1 and r['items'][0]['title']=='Budget 100% 2'
    assert client.get('/api/v1/articles?q=100_').json()['total']==0
    assert client.get('/api/v1/articles?sort=oldest&limit=1').json()['items'][0]['title']=='Budget 100% 0'
    assert client.get('/api/v1/articles?sort=published_newest&limit=1').json()['items'][0]['title']=='Budget 100% 3'
    assert client.get('/api/v1/articles?date_from=2026-10-20&date_field=discovered').json()['total']==5
    assert client.get('/api/v1/articles?category=business').json()['total']==0

def test_semantic_fallback_preserves_scope(client,db,monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings,'ai_enabled',False);seed(db)
    r=client.get('/api/v1/semantic-search?q=Budget&domain=ikon.mn&date_from=2026-10-19&date_to=2026-10-19').json()
    assert client.get('/api/v1/semantic-search?q=Budget&offset=1001').status_code==200
    assert r['mode']=='lexical_fallback' and r['total']==1 and r['items'][0]['title']=='Budget 100% 2'
    assert client.get('/api/v1/semantic-search?q=x&date_from=2026-10-20&date_to=2026-10-19').status_code==422

def test_web_links_filtered_dates_and_options(client):
    from urllib.parse import urlsplit,parse_qs
    r=client.get('/api/v1/media/search?q=budget&category=business&date_from=2026-10-01&date_to=2026-10-19').json()
    assert r['total_sites']>0
    assert parse_qs(urlsplit(r['items'][0]['url']).query)['tbs']==['cdr:1,cd_min:10/01/2026,cd_max:10/19/2026']
    assert client.get('/api/v1/media/search?q=x&engine=bing&date_from=2026-10-01').status_code==422
    assert client.get('/api/v1/media/search?q=x&availability=active').json()['total_sites']==0
    assert len(client.get('/api/v1/media/options').json()['items'])>=400
