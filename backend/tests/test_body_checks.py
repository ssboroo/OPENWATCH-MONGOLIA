import asyncio,json
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from app.models import Source,Article,ArticleVersion,ArticleBodyCheck
from app.collector import ingest
from app import body_checks as bc
from test_archive import client,db

BODY=' '.join(f'Төсөл {i} иргэдийн санал болон төсвийн тайланг нийтэд нээлттэй танилцуулж байна.' for i in range(20))
OTHER=' '.join(f'Спорт {i} тамирчид тэмцээнээр олон улсын аваргын медаль хүртсэн амжилт гаргалаа.' for i in range(20))

def html(body=BODY,label=''):
    return f'<html><nav>{OTHER}</nav>{label}<article><h1>Fixture title</h1><div itemprop="articleBody"><p>{body}</p></div><aside>{OTHER}</aside></article></html>'.encode()

def seed(db,active=True):
    ss=[Source(name='iKon fixture',endpoint='https://ikon.mn/rss',active=active),Source(name='GoGo fixture',endpoint='https://gogo.mn/rss',active=active)]
    db.add_all(ss);db.flush()
    for i,s in enumerate(ss):ingest(db,s,[{'url':s.endpoint.replace('rss','news/fixture'),'title':'Улсын төсвийн шинэ тайлан нийтлэгдлээ' if not i else 'Засгийн газар төсвийн мэдээллээ танилцуулав','excerpt':'','published_at':None,'updated_at':None}])
    db.commit();return list(db.scalars(select(Article).order_by(Article.id)))

def test_body_container_and_jsonld_graph():
    data=bc.extract_body(html())
    assert data and data['word_count']>40 and len(data['signature'])<=256
    assert 'Спорт' not in data['lead'] and 'Fixture title' not in data['lead']
    raw=('<script type="application/ld+json">'+json.dumps({'@graph':[{'@type':['NewsArticle'],'articleBody':BODY}]})+'</script>').encode()
    assert bc.extract_body(raw)['body_hash']==data['body_hash']
    assert bc.extract_body(b'<nav>hello</nav><p>just a short generic navigation</p>') is None
    # A precise articleBody wins over unrelated surrounding article text.
    assert bc.extract_body(html().replace(b'</article>',f'<p>{OTHER}</p></article>'.encode()))['body_hash']==data['body_hash']

def test_explicit_disclosure_and_not_just_discussing_ads():
    d=bc.extract_body(html(label='<span class="article-label">Төлбөртэй мэдээ</span>'))
    assert d['disclosures'][0]['quote']=='Төлбөртэй мэдээ'
    assert not bc.extract_body(html('Сурталчилгааны тухай мэдээ. '+BODY))['disclosures']
    assert not bc.extract_body(html('Сурталчилгаа: Энэ салбарын талаар ярилцлаа. '+BODY))['disclosures']
    assert bc.extract_body(html('Paid content: '+BODY))['disclosures']

def test_body_equal_with_different_title_and_no_copy_direction(db,client,monkeypatch):
    rows=seed(db);monkeypatch.setattr(bc,'Session',sessionmaker(db.bind,expire_on_commit=False))
    async def fetch(url):return html()
    for a in rows:assert asyncio.run(bc.check_article(a.id,fetch))['state']=='ready'
    d=client.get(f'/api/v1/articles/{rows[0].id}/comparison').json()
    assert d['items'][0]['comparison']=='normalized_body_equal'
    assert d['items'][0]['body_similarity']==1 and d['items'][0]['title_similarity']<1
    assert d['items'][0]['shared_passages'][0]['quote'] in BODY
    assert not d['items'][0]['same_site']
    assert d['body']['disclosure']=='not_observed'
    assert 'хэн хэнээс хуулсныг тогтоохгүй' in d['limitation']
    assert client.get('/api/v1/comparison/status').json()['ready']==2
    # The whole source body is never retained.
    c=db.get(ArticleBodyCheck,rows[0].id);assert len(c.data['lead'])<=600 and BODY not in json.dumps(c.data,ensure_ascii=False)

def test_identical_headline_with_different_body_is_not_full_copy(db,client,monkeypatch):
    rows=seed(db);rows[1].title=rows[0].title;db.commit()
    monkeypatch.setattr(bc,'Session',sessionmaker(db.bind,expire_on_commit=False))
    async def fetch(url):return html(BODY if 'ikon' in url else OTHER)
    for a in rows:asyncio.run(bc.check_article(a.id,fetch))
    d=client.get(f'/api/v1/articles/{rows[0].id}/comparison').json()
    assert d['items'][0]['comparison']=='title_only_candidate'
    assert d['items'][0]['body_similarity']<.45
    assert d['items'][0]['body']['state']=='ready'

def test_unknown_body_and_changed_version_do_not_inherit_full_copy(db,client,monkeypatch):
    rows=seed(db);rows[1].title=rows[0].title;db.commit()
    d=client.get('/api/v1/articles/1/comparison').json()
    assert d['body']['state']=='not_checked' and d['items'][0]['body_similarity'] is None
    monkeypatch.setattr(bc,'Session',sessionmaker(db.bind,expire_on_commit=False))
    async def fetch(url):return html()
    for a in rows:asyncio.run(bc.check_article(a.id,fetch))
    a=db.get(Article,2);a.version=2;a.text_hash='x'*64
    db.add(ArticleVersion(article_id=2,version=2,title=a.title,excerpt='',text_hash=a.text_hash));db.commit()
    assert client.get('/api/v1/articles/1/comparison').json()['items'][0]['body']['state']=='not_checked'
    assert client.get('/api/v1/articles/2/comparison').json()['body']['state']=='not_checked'

def test_robots_failure_and_inactive_source_not_read(db,monkeypatch):
    rows=seed(db);monkeypatch.setattr(bc,'Session',sessionmaker(db.bind,expire_on_commit=False))
    async def blocked(url):raise ValueError('robots.txt disallows collection')
    assert asyncio.run(bc.check_article(1,blocked))['state']=='blocked'
    s=db.get(Source,rows[1].source_id);s.active=False;db.commit()
    async def never(url):raise AssertionError('Inactive source must not be fetched')
    assert asyncio.run(bc.check_article(2,never))['state']=='source_inactive'

def test_overlap_and_truncation():
    a=bc.extract_body(html());b=bc.extract_body(html(BODY+' '+OTHER))
    score=bc.body_overlap(a,b)
    assert .3<score<.8
    assert bc.body_overlap(a,bc.extract_body(html(OTHER)))<.2
    assert bc.extract_body(html(BODY*200))['truncated'] is True

def test_paywall_not_bypassed_and_title_anchored_fallback():
    raw=('<script type="application/ld+json">'+json.dumps({'@type':'NewsArticle','isAccessibleForFree':False,'articleBody':BODY})+'</script>').encode()
    assert bc.extract_body(raw) is None
    raw=f'<main><div><h1>Улсын төсвийн шинэ тайлан</h1><div><p>{BODY}</p></div></div></main>'.encode()
    assert bc.extract_body(raw,'Улсын төсвийн шинэ тайлан')
    assert bc.extract_body(raw,'Спортын аваргын шинэ мэдээ') is None

def test_fixed_id_content_job_limits(client,db,monkeypatch):
    rows=seed(db,active=False);bc.JOBS.clear()
    assert client.post('/api/v1/articles/99999/content-check').status_code==404
    bc.JOBS.update({9001,9002})
    try:assert client.post('/api/v1/articles/1/content-check').status_code==429
    finally:bc.JOBS.clear()
    async def no_network(id):bc.JOBS.discard(id)
    monkeypatch.setattr(bc,'check_with_neighbors',no_network)
    for id in [1,2,1]:assert client.post(f'/api/v1/articles/{id}/content-check').status_code==202
    assert client.post('/api/v1/articles/2/content-check').status_code==429

def test_wordpress_infinite_next_article_not_part_of_main_body():
    raw=f'<article><div id="mvp-content-main"><p>{BODY}</p></div><div class="mvp-post-add-main"><p>{OTHER}</p></div></article>'.encode()
    data=bc.extract_body(raw)
    assert data['body_hash']==bc.extract_body(html())['body_hash']

def test_commercial_language_is_not_a_paid_verdict():
    data=bc.extract_body(html(BODY+' Та одоо худалдан аваарай. Эх сурвалж: Нийтлэгчийн хэвлэлийн алба.'))
    assert data['promotion_signals'][0]['phrase']=='худалдан аваарай'
    assert not data['disclosures']
    assert data['source_credits'] and 'Нийтлэгчийн' in data['source_credits'][0]

def test_comparison_groups_equal_body_changed_headline_filters_and_paging(db,client,monkeypatch):
    rows=seed(db);monkeypatch.setattr(bc,'Session',sessionmaker(db.bind,expire_on_commit=False))
    async def fetch(url):return html()
    for a in rows:asyncio.run(bc.check_article(a.id,fetch))
    d=client.get('/api/v1/comparison/groups?kind=exact&domain=ikon.mn&limit=1').json()
    assert d['total']==1 and len(d['items'])==1
    g=d['items'][0]
    assert g['article_count']==2 and g['exact_families']==[[2,1]]
    assert g['domains']==['gogo.mn','ikon.mn'] and g['ready_count']==2
    assert client.get('/api/v1/comparison/groups?offset=1&limit=1').json()['items']==[]
    assert client.get('/api/v1/comparison/groups?q=not-present').json()['total']==0
    c=db.get(ArticleBodyCheck,rows[1].id);c.data={**c.data,'adapter':'old-adapter'};db.commit()
    assert client.get('/api/v1/comparison/groups?kind=exact').json()['total']==0

def test_explicit_pair_shows_unrelated_and_unread_instead_of_omitting(db,client,monkeypatch):
    rows=seed(db)
    d=client.get('/api/v1/articles/1/comparison?other_id=2').json()
    assert len(d['items'])==1 and d['items'][0]['comparison']=='insufficient_body'
    monkeypatch.setattr(bc,'Session',sessionmaker(db.bind,expire_on_commit=False))
    async def fetch(url):return html(BODY if 'ikon' in url else OTHER)
    for a in rows:asyncio.run(bc.check_article(a.id,fetch))
    d=client.get('/api/v1/articles/1/comparison?other_id=2').json()
    assert len(d['items'])==1 and d['items'][0]['comparison']=='no_strong_match'
    assert client.get('/api/v1/articles/1/comparison?other_id=1').status_code==422
    assert client.get('/api/v1/articles/1/comparison?other_id=99999').status_code==422

def test_groups_titles_are_not_full_body_verdicts(db,client):
    rows=seed(db);rows[1].title=rows[0].title;db.commit()
    d=client.get('/api/v1/comparison/groups?kind=cross_site').json()
    assert d['total']==1
    assert d['items'][0]['exact_families']==[] and d['items'][0]['ready_count']==0
    assert 'title_equal' in d['items'][0]['methods']
    assert client.get('/api/v1/comparison/groups?kind=exact').json()['total']==0
