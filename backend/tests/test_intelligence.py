import asyncio
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from app.models import Source,Article,ArticleVersion,ArticleEmbedding,EntityMention
from app.collector import ingest
from app.evidence import add_entity
from app.config import settings
from app import pipeline,worker
from app.ai import Extraction,InferenceFailure
from test_archive import client,db

class Contract:
    async def extract(self,text):
        title=text.split('\n')[0]
        return Extraction(summary_quotes=[title],entities=[{'kind':'organization','name':'Монголбанк','quote':title}],claims=[],category='economy',confidence=.5)
    async def embed(self,text):return [1.0]+[0.0]*1023

def seed(db,n=2):
    s=Source(name='Headline fixture',endpoint='https://ikon.mn/');db.add(s);db.flush()
    for i in range(n):ingest(db,s,[{'url':f'https://ikon.mn/n/{i}','title':f'Монголбанк бодлогын хүүг хэлэлцэж байна {i}','excerpt':'','published_at':None,'updated_at':None,'source_metadata':{'metadata_only':True}}])
    db.commit()

def test_headline_ai_backfill_fairness_and_source_cited_connections(db,client,monkeypatch):
    seed(db,5)
    monkeypatch.setattr(pipeline,'Session',sessionmaker(db.bind,expire_on_commit=False))
    monkeypatch.setattr(settings,'ai_enabled',True);monkeypatch.setattr(settings,'ai_batch_size',100)
    result=asyncio.run(pipeline.process_batch(Contract()))
    assert [x['article_id'] for x in result['items']]==[5,4,1,2]
    assert all(x['status']=='ai_complete' for x in result['items'])
    assert [x['article_id'] for x in asyncio.run(pipeline.process_batch(Contract()))['items']]==[3]
    d=client.get('/api/v1/articles/1/analysis').json()
    assert d['items'][0]['scope']=='headline_only'
    assert 'бүтэн эхийг уншаагүй' in d['items'][0]['limitation']
    related=d['connections']
    assert related['entities'][0]['name']=='Монголбанк'
    assert len(related['related'])==4
    assert all(x['reasons'] and x['url'].startswith('https://') for x in related['related'])
    assert {r['method'] for x in related['related'] for r in x['reasons']}=={'shared_name_candidate','embedding_cosine'}
    # A changed current version must not inherit the old version's entity link or vector.
    a=db.get(Article,2);a.version=2;a.title='Өөр шинэ мэдээ';a.text_hash='z'*64
    db.add(ArticleVersion(article_id=2,version=2,title=a.title,excerpt='',text_hash=a.text_hash));db.commit()
    d=client.get('/api/v1/articles/1/connections').json()
    assert 2 not in {x['id'] for x in d['related']}
    assert client.get('/api/v1/articles/2/analysis').json()['items']==[]
    assert client.get('/api/v1/articles/999/connections').status_code==404

def test_failed_generation_does_not_mark_embedding_as_full_ai_completion(db,monkeypatch):
    seed(db,1)
    monkeypatch.setattr(pipeline,'Session',sessionmaker(db.bind,expire_on_commit=False));monkeypatch.setattr(settings,'ai_enabled',True)
    class Partial(Contract):
        async def embed(self,text):raise InferenceFailure('offline')
    assert asyncio.run(pipeline.analyze_article(1,Partial()))['status']=='ai_unavailable'
    with sessionmaker(db.bind)() as check:
        assert check.get(Article,1).ai_hash is None
        assert check.scalar(select(EntityMention)) is not None

def test_slow_collection_does_not_block_analysis(db,monkeypatch):
    monkeypatch.setattr(worker,'Session',sessionmaker(db.bind,expire_on_commit=False));monkeypatch.setattr(settings,'ai_enabled',False)
    async def check():
        collection_started=asyncio.Event();analysis_started=asyncio.Event();release=asyncio.Event()
        async def collect():collection_started.set();await release.wait();return {'status':'done'}
        async def process():await collection_started.wait();analysis_started.set();return {'status':'done'}
        monkeypatch.setattr(worker,'collect',collect);monkeypatch.setattr(worker,'process_batch',process)
        tasks=[asyncio.create_task(worker.collection_loop()),asyncio.create_task(worker.analysis_loop())]
        try:await asyncio.wait_for(analysis_started.wait(),1)
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
    asyncio.run(check())


def test_rejected_extraction_still_indexes_semantic_text(db,monkeypatch):
    seed(db,1)
    monkeypatch.setattr(pipeline,'Session',sessionmaker(db.bind,expire_on_commit=False));monkeypatch.setattr(settings,'ai_enabled',True)
    class Partial(Contract):
        async def extract(self,text):raise InferenceFailure('ungrounded model output rejected')
    assert asyncio.run(pipeline.analyze_article(1,Partial()))['status']=='ai_unavailable'
    with sessionmaker(db.bind)() as check:
        assert check.get(ArticleEmbedding,1) is not None
        assert check.get(Article,1).ai_hash is None
