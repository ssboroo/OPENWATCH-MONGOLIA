import asyncio
import json
from datetime import timedelta
from sqlalchemy import select
from app.importers import parse_source
from app.models import *
from app.collector import ingest
from app.operations import retain_versions
from app.reports import build_report
from test_reports import populate
from test_archive import db,client
import pytest

def test_open_json_csv_and_sitemap():
    row={'url':'https://ikon.mn/a','title':'Гарчиг','summary':'Товч','published_at':'2026-10-19T10:00:00+08:00'}
    parsed=parse_source(json.dumps({'items':[row]}).encode(),'json')
    assert parsed[0]['published_at'].hour==2
    csv='url,title,summary,published_at\nhttps://ikon.mn/a,Гарчиг,Товч,2026-10-19T02:00:00Z\n'.encode()
    assert parse_source(csv,'csv')[0]['title']=='Гарчиг'
    xml=b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://ikon.mn/a</loc><lastmod>2026-10-19</lastmod></url></urlset>'
    result=parse_source(xml,'sitemap','https://ikon.mn/sitemap.xml')[0]
    assert result['published_at'] is None and result['source_metadata']['metadata_only']
    with pytest.raises(ValueError):parse_source(xml,'sitemap','https://gogo.mn/sitemap.xml')
    row['published_at']='2026-10-19T10:00:00'
    with pytest.raises(ValueError):parse_source(json.dumps([row]).encode(),'json')

def test_retention_keeps_current_and_published_evidence(db):
    event=populate(db);r=build_report(db,event.id);r.state='published';db.flush()
    article=db.scalar(select(Article));source=db.get(Source,article.source_id)
    old=db.scalar(select(ArticleVersion).where(ArticleVersion.article_id==article.id));old.observed_at=now()-timedelta(days=365)
    ingest(db,source,[{'title':'Шинэ гарчиг','excerpt':'Шинэ агуулга','url':article.url,'published_at':None,'updated_at':None}]);db.flush()
    result=retain_versions(db,False)
    assert old.id not in result['eligible_version_ids'] and db.get(ArticleVersion,old.id)
    r.state='draft';db.flush()
    assert old.id in retain_versions(db,True)['eligible_version_ids']
    retain_versions(db,False);db.flush()
    assert db.get(ArticleVersion,old.id) is None
    assert db.scalar(select(ArticleVersion).where(ArticleVersion.article_id==article.id,ArticleVersion.version==2))

def test_semantic_search_labels_offline_fallback(client,db):
    populate(db);db.commit()
    result=client.get('/api/v1/semantic-search?q=төсөв').json()
    assert result['mode']=='lexical_fallback' and result['total']==2
    assert client.get('/api/v1/semantic-search?q=төсөв&domain=evil.local').status_code==422

def test_system_status_empty_worker_is_stale(client):
    response=client.get('/api/v1/system/status')
    assert response.status_code==200 and response.json()['worker_stale'] is True

def test_http_body_size_limit(client):
    r=client.post('/api/v1/reports/1/corrections',content=b'x'*70000,headers={'Content-Type':'application/json'})
    assert r.status_code==413

def test_fts_falls_back_on_sqlite(client,db):
    populate(db);db.commit()
    r=client.get('/api/v1/search?q=төсөв&mode=fts')
    assert r.status_code==200 and r.json()['mode']=='lexical' and r.json()['total']==2

def test_internal_metrics_do_not_contain_secrets(client):
    r=client.get('/metrics')
    assert r.status_code==200 and 'openwatch_worker_stale 1' in r.text
    assert 'ADMIN_TOKEN' not in r.text and 'DATABASE_URL' not in r.text

def test_sitemap_upgrades_to_real_feed_without_losing_first_seen_or_provenance(db):
    sitemap=Source(name='Sitemap',endpoint='https://ikon.mn/sitemap.xml',kind='sitemap')
    feed=Source(name='Feed',endpoint='https://ikon.mn/rss',kind='rss')
    db.add_all([sitemap,feed]);db.flush()
    ingest(db,sitemap,[{'url':'https://ikon.mn/item','title':'[Гарчиг татаагүй] /item','excerpt':'','published_at':None,'updated_at':None,'source_metadata':{'metadata_only':True}}]);a=db.scalar(select(Article));first=a.first_seen_at
    ingest(db,feed,[{'url':'https://ikon.mn/item','title':'Жинхэнэ feed гарчиг','excerpt':'Эхийн богино хэсэг','published_at':None,'updated_at':None}]);db.flush()
    assert a.version==2 and a.source_id==feed.id and a.first_seen_at==first
    versions=list(db.scalars(select(ArticleVersion).where(ArticleVersion.article_id==a.id).order_by(ArticleVersion.version)))
    assert [v.source_id for v in versions]==[sitemap.id,feed.id]
