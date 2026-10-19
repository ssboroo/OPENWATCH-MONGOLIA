from test_archive import client, db
from app.models import Source, Article, ArticleVersion
from app.collector import ingest

def seed(db):
    s=Source(name='iKon',endpoint='https://ikon.mn/rss');db.add(s);db.flush()
    for i,title,excerpt in [(1,'Budget 25 хувь public notice','Allocation 50 сая төгрөг. Contact test@example.com'),(2,'Budget headline only','')]:
        ingest(db,s,[{'title':title,'excerpt':excerpt,'url':f'https://ikon.mn/n/test{i}','published_at':None,'updated_at':None,'source_metadata':{}}])
    db.commit()

def test_exact_version_evidence_and_unverified_claims(client,db):
    seed(db)
    r=client.get('/api/v1/research',params={'q':'public Budget'}).json()
    assert r['total']==1
    item=r['items'][0]
    assert item['published_at'] is None and item['scope']=='title_and_excerpt'
    v=db.get(ArticleVersion,item['version_id']);text=v.title+'\n'+v.excerpt
    for q in item['quotes']:
        if not q['redacted']:assert text[q['start_offset']:q['end_offset']]==q['text']
    assert 'test@example.com' not in str(r)
    assert {c['kind'] for c in item['claims']}=={'percentage','money'}
    assert all(c['status']=='unverified' for c in item['claims'])
    assert item['text_hash']==v.text_hash

def test_scope_pagination_unknown_dates_and_headlines(client,db):
    seed(db)
    r=client.get('/api/v1/research?q=Budget&limit=1').json()
    assert r['total']==2 and len(r['items'])==1
    assert r['items'][0]['scope']=='headline_only'
    assert client.get('/api/v1/research?q=Budget&category=official').json()['total']==0
    assert client.get('/api/v1/research?q=Budget&domain=gogo.mn').json()['total']==0
    assert client.get('/api/v1/research?q=Budget&date_field=published&date_from=2020-01-01').json()['total']==0
    assert client.get('/api/v1/research?q=Budget&date_field=discovered&date_from=2020-01-01').json()['total']==2
    assert client.get('/api/v1/research?q=100%25').json()['total']==0
    assert client.get('/api/v1/research?q=%20%20').status_code==422
    assert client.get('/api/v1/research?q=x&date_from=2026-10-20&date_to=2026-10-19').status_code==422
    assert client.get('/api/v1/research?q=x&limit=51').status_code==422

def test_current_version_only(client,db):
    seed(db)
    a=db.query(Article).filter(Article.url=='https://ikon.mn/n/test1').one()
    a.version=2;a.title='Correction';a.excerpt='';a.text_hash='b'*64
    db.add(ArticleVersion(article_id=a.id,version=2,title='Correction',excerpt='',text_hash=a.text_hash));db.commit()
    assert client.get('/api/v1/research?q=public').json()['total']==0
    assert client.get('/api/v1/research?q=Correction').json()['items'][0]['version']==2
