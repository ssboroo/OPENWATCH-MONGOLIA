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


def advanced_seed(db):
    from app.models import ArticleVersion,ArticleBodyCheck
    from app.body_checks import VERSION
    s=Source(name='Public fixture',endpoint='https://ikon.mn/rss');db.add(s);db.flush()
    rows=[]
    for i,(title,excerpt,state) in enumerate([
        ('Budget new law','Official evidence 100%','ai_complete'),
        ('New budget','Sport report','pending'),
        ('Other subject','Budget law evidence','ai_unavailable'),
        ('Budget law','Other archive','metadata_only'),
    ]):
        a=Article(source_id=s.id,url=f'https://ikon.mn/advanced/{i}',title=title,excerpt=excerpt,text_hash=str(i)*64,analysis_status=state,published_at=datetime(2026,10,19,tzinfo=timezone.utc) if i%2==0 else None)
        db.add(a);db.flush();v=ArticleVersion(article_id=a.id,version=1,title=title,excerpt=excerpt,text_hash=a.text_hash);db.add(v);db.flush();rows.append(a)
        if i in (0,1,2):
            db.add(ArticleBodyCheck(article_id=a.id,article_version_id=v.id,state='ready',body_hash='a'*64,data={'adapter':VERSION if i!=2 else 'outdated'}))
    rows[1].version=2
    db.add(ArticleVersion(article_id=rows[1].id,version=2,title=rows[1].title,excerpt=rows[1].excerpt,text_hash=rows[1].text_hash))
    db.commit()
    return rows


def test_advanced_words_fields_and_exclusions(client,db):
    advanced_seed(db)
    def count(**params):return client.get('/api/v1/articles',params=params).json()['total']
    assert count(q='budget law',match='all')==3
    assert count(q='budget law',match='phrase')==2
    assert count(q='sport absent',match='any')==1
    assert count(q='budget',field='title')==3
    assert count(q='budget',field='excerpt')==1
    assert count(q='budget',exclude='sport')==3
    assert count(q='budget',exclude='sport official')==2
    assert count(q='100%')==1 and count(q='100_')==0
    assert client.get('/api/v1/articles',params={'match':'invalid'}).status_code==422
    assert client.get('/api/v1/articles',params={'q':' '.join('word'+str(i) for i in range(21)),'match':'all'}).status_code==422


def test_advanced_processing_filters_respect_current_version(client,db):
    advanced_seed(db)
    def titles(**params):return {a['title'] for a in client.get('/api/v1/articles',params=params).json()['items']}
    assert titles(body='ready')=={'Budget new law'}
    assert len(titles(body='unread'))==3
    assert titles(analysis='complete',body='ready',publication='known')=={'Budget new law'}
    assert titles(analysis='pending',publication='unknown')=={'New budget','Budget law'}
    assert titles(analysis='unavailable')=={'Other subject'}
    assert client.get('/api/v1/articles?body=unrecognized').status_code==422


def test_semantic_offline_keeps_advanced_conditions(client,db,monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings,'ai_enabled',False);advanced_seed(db)
    r=client.get('/api/v1/semantic-search',params={'q':'budget law','match':'all','exclude':'other','analysis':'complete','body':'ready','publication':'known'}).json()
    assert r['mode']=='lexical_fallback' and r['total']==1
    assert r['items'][0]['title']=='Budget new law'


def test_read_body_lead_search_is_version_grounded(client,db):
    from app.models import ArticleBodyCheck
    rows=advanced_seed(db)
    for a in rows[:2]:
        c=db.get(ArticleBodyCheck,a.id);c.data={**c.data,'lead':'Unique publisher lead proof'}
    db.commit()
    r=client.get('/api/v1/articles?q=Unique&field=body').json()
    assert r['total']==1 and r['items'][0]['id']==rows[0].id
    assert r['items'][0]['body_lead']=='Unique publisher lead proof'
    assert client.get('/api/v1/articles?q=Unique&field=all').json()['total']==1
    assert client.get('/api/v1/articles?q=Unique&field=title').json()['total']==0
    assert client.get('/api/v1/articles?q=Budget&exclude=Unique').json()['total']==3

def test_freshness_uses_publication_not_newly_discovered(db):
    from datetime import timedelta
    from sqlalchemy import select
    from app.models import Source,Article,now
    from app.search_filters import fresh
    s=Source(name='fresh-test',endpoint='https://ikon.mn/fresh-test');db.add(s);db.flush()
    dates=[now()-timedelta(hours=1),now()-timedelta(days=3),now()-timedelta(days=1000),None,now()+timedelta(days=1)]
    for i,d in enumerate(dates):db.add(Article(source_id=s.id,url=f'https://ikon.mn/fresh-test/{i}',title=str(i),excerpt='',text_hash=str(i)*64,published_at=d,first_seen_at=now()))
    db.commit()
    assert [a.title for a in db.scalars(fresh(select(Article),db,'48h'))]==['0']
    assert {a.title for a in db.scalars(fresh(select(Article),db,'7d'))}=={'0','1'}
    assert len(list(db.scalars(fresh(select(Article),db,'all'))))==5
