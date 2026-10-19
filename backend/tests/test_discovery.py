import asyncio
import pytest
from sqlalchemy import select,func
from app.importers import parse_source
from app.models import Source,Article,SystemState
from test_archive import db

HTML=b'''<html><nav><h2><a href="/category/news">This is navigation and not an article headline</a></h2></nav><main>
<article><a href="/news/one"><h2>First public budget report for the entire country</h2></a></article>
<h2><a href="/news/two">Second public report from the original publisher</a></h2>
<a href="/news/three"><h3>Third public report with a readable news headline</h3></a>
<h2><a href="https://evil.example/stolen">External content must never enter the publisher archive</a></h2>
<h2><a href="/category/long">This is still a category and must not become news</a></h2>
<h2><a href="/news/one">Duplicate article headline should not be repeated here</a></h2></main></html>'''

def test_public_headline_extraction_has_origin_and_metadata_provenance():
    rows=parse_source(HTML,'html','https://ikon.mn/')
    assert len(rows)==3 and all(r['url'].startswith('https://ikon.mn/news/') for r in rows)
    assert all(r['published_at'] is None and r['excerpt']=='' and r['source_metadata']['headline_only'] for r in rows)
    with pytest.raises(ValueError):parse_source(b'<nav><h2>Only a menu</h2></nav>','html','https://ikon.mn/')

def test_news_sitemap_preserves_publisher_title():
    raw=b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"><url><loc>https://ikon.mn/n/a</loc><news:news><news:title>Original title supplied by publisher</news:title></news:news></url></urlset>'''
    row=parse_source(raw,'sitemap','https://ikon.mn/news-sitemap.xml')[0]
    assert row['title']=='Original title supplied by publisher' and row['source_metadata']['sitemap_has_title']

def test_commission_registers_without_full_text_and_preserves_records(db,monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app import discovery
    monkeypatch.setattr(discovery,'Session',sessionmaker(db.bind,expire_on_commit=False))
    site={'name':'iKon','domain':'ikon.mn'}
    result=discovery.register(site,'https://ikon.mn/','html',parse_source(HTML,'html','https://ikon.mn/'))
    assert result['status']=='active' and result['added']==3
    assert discovery.register(site,'https://ikon.mn/','html',parse_source(HTML,'html','https://ikon.mn/'))['added']==0
    assert db.scalar(select(func.count()).select_from(Article))==3
    assert db.scalar(select(Source)).active

def test_scan_resumes_and_one_bad_host_does_not_abort(db,monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app import discovery
    monkeypatch.setattr(discovery,'Session',sessionmaker(db.bind,expire_on_commit=False))
    monkeypatch.setattr(discovery,'SITES',[{'domain':'one.mn'},{'domain':'two.mn'},{'domain':'three.mn'}])
    monkeypatch.setattr(discovery,'probe_results',lambda:{})
    calls=[]
    async def inspect(site,probe):
        calls.append(site['domain'])
        if site['domain']=='two.mn':raise ValueError('Unavailable')
        return {'status':'active','format':'html'}
    monkeypatch.setattr(discovery,'inspect',inspect)
    asyncio.run(discovery.commission());asyncio.run(discovery.commission())
    assert len(calls)==3
    states=list(db.scalars(select(SystemState).where(SystemState.name.like('discovery:%'))))
    assert len(states)==3 and sum(s.value['status']=='unavailable' for s in states)==1
    assert db.get(SystemState,'catalog_discovery').value['status']=='completed'

def test_plain_article_id_links_without_headings():
    html=b'<main><a href="/n/abcd">Plain publisher headline with an article identifier</a><a href="/n/efgh">Another public headline with no heading markup</a><a href="/n/ijkl">Third real article link from a publisher homepage</a><a href="/category/politics">Navigation category must never enter the archive</a></main>'
    rows=parse_source(html,'html','https://ikon.mn/')
    assert len(rows)==3 and all('/n/' in r['url'] for r in rows)
