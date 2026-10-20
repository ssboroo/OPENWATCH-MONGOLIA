import asyncio
from datetime import timedelta
from sqlalchemy import select,func
from sqlalchemy.orm import sessionmaker
from app.models import *
from app.collector import ingest
from app.clustering import rebuild_events, canonical_event
from app.evidence import lexical_claims, evidence_for, add_entity
from app.reports import build_report
from app import pipeline
from app.ai import InferenceFailure
from app.config import settings
from test_archive import client,db


def populate(db):
    source=Source(name='Test newsroom',endpoint='https://ikon.mn/rss',license='Test terms',permission_note='Test fixture only');db.add(source);db.flush()
    for i,value in enumerate(['400','500']):
        ingest(db,source,[{'title':'Улсын шинэ төсвийн тухай мэдээлэл','excerpt':f'Улсын шинэ төсөв {value} сая төгрөг.','url':f'https://ikon.mn/item/{i}','published_at':now()-timedelta(hours=2-i),'updated_at':None}])
    rebuild_events(db);db.flush()
    for article in db.scalars(select(Article)):
        version=db.scalar(select(ArticleVersion).where(ArticleVersion.article_id==article.id))
        lexical_claims(db,article,version);evidence_for(db,article,version,version.title)
    db.flush();return db.scalar(select(Event).where(Event.merged_into_id.is_(None)))

def headers(monkeypatch):
    monkeypatch.setattr(settings,'admin_token','x'*32)
    return {'Authorization':'Bearer '+'x'*32}

def test_stable_event_and_immutable_report(db):
    event=populate(db);report=build_report(db,event.id);db.commit();eid=event.id;digest=report.body_hash
    assert report.body['discrepancies'] and report.finding=='sources_differ'
    assert all(e['url'].startswith('https://ikon.mn/') for e in report.body['evidence'])
    assert report.body['timeline'][0]['minutes_after_earliest_observed_publication']==0
    rebuild_events(db);db.commit()
    assert canonical_event(db,eid).id==eid
    assert build_report(db,eid).id==report.id
    assert report.body_hash==digest
    assert report.state=='draft'

def test_publish_review_correction_withdraw_flow(client,db,monkeypatch):
    from app.main import submission_buckets
    submission_buckets.clear()
    event=populate(db);report=build_report(db,event.id);db.commit();auth=headers(monkeypatch)
    assert client.get('/api/v1/reports?freshness=all').json()['total']==0
    assert client.get(f'/api/v1/reports/{report.id}').status_code==404
    body={'decision':'publish','expected_hash':report.body_hash,'note':'Source links and private information reviewed.','privacy_checked':False,'finding':'sources_differ'}
    assert client.post(f'/api/v1/admin/reports/{report.id}/review',json=body).status_code==401
    assert client.post(f'/api/v1/admin/reports/{report.id}/review',json=body,headers=auth).status_code==422
    body['privacy_checked']=True;body['expected_hash']='0'*64
    assert client.post(f'/api/v1/admin/reports/{report.id}/review',json=body,headers=auth).status_code==409
    body['expected_hash']=report.body_hash
    assert client.post(f'/api/v1/admin/reports/{report.id}/review',json=body,headers=auth).json()['state']=='published'
    public=client.get(f'/api/v1/reports/{report.id}').json()
    assert public['body']['evidence'][0]['url'].startswith('https://ikon.mn/')
    submitted=client.post(f'/api/v1/reports/{report.id}/corrections',json={'text':'Энэ мөнгөн дүн өөр хугацааны төсөвтэй холбоотой.','evidence_urls':['https://ikon.mn/document']})
    assert submitted.status_code==201
    cid=submitted.json()['id']
    assert client.get(f'/api/v1/reports/{report.id}').json()['corrections']==[]
    assert client.get(f'/api/v1/reports/{report.id}').json()['correction_pending'] is True
    response={'decision':'accepted','response':'Залруулгыг эх баримтаар шалгаж хавсаргав.','privacy_checked':True}
    assert client.post(f'/api/v1/admin/corrections/{cid}/review',headers=auth,json=response).status_code==200
    assert client.get(f'/api/v1/reports/{report.id}').json()['corrections'][0]['id']==cid
    body['decision']='withdraw'
    assert client.post(f'/api/v1/admin/reports/{report.id}/review',json=body,headers=auth).status_code==200
    withdrawn=client.get(f'/api/v1/reports/{report.id}').json()
    assert withdrawn['state']=='withdrawn' and withdrawn['body'] is None

def test_graph_links_have_evidence(db,client):
    event=populate(db);article=db.scalar(select(Article));version=db.scalar(select(ArticleVersion).where(ArticleVersion.article_id==article.id))
    add_entity(db,article,version,'organization','Улсын',version.title,.5);db.commit()
    graph=client.get(f'/api/v1/events/{event.id}/graph').json()
    assert graph['nodes'] and graph['links']
    assert all(link.get('evidence_url') for link in graph['links'])
    assert any(link['relation']=='mentions' and link['quote'] for link in graph['links'])

def test_offline_pipeline_keeps_archive_and_drafts(db,monkeypatch):
    event=populate(db);db.commit()
    monkeypatch.setattr(pipeline,'Session',sessionmaker(db.bind,expire_on_commit=False))
    monkeypatch.setattr(settings,'ai_enabled',True)
    class Offline:
        async def extract(self,text):raise InferenceFailure('offline')
        async def embed(self,text):raise InferenceFailure('offline')
    result=asyncio.run(pipeline.process_batch(Offline()))
    assert result['status']=='completed' and result['draft_report_ids']
    with sessionmaker(db.bind)() as check:
        assert check.scalar(select(func.count()).select_from(Article))==2
        assert check.scalar(select(func.count()).select_from(AnalysisRun).where(AnalysisRun.status=='fallback'))==2
        assert check.scalar(select(func.count()).select_from(PublicReport).where(PublicReport.state=='published'))==0

def test_public_redaction(client,db):
    s=Source(name='Fixture',endpoint='https://ikon.mn/rss');db.add(s);db.flush()
    ingest(db,s,[{'title':'Холбогдох утас 99112233','excerpt':'И-мэйл secret@example.com, регистр АБ12345678','url':'https://ikon.mn/redaction','published_at':None,'updated_at':None}]);db.commit()
    data=client.get('/api/v1/articles?freshness=all').json()['items'][0]
    assert '99112233' not in data['title'] and 'secret@example.com' not in data['excerpt'] and 'АБ12345678' not in data['excerpt']
    assert data['url']=='https://ikon.mn/redaction'

def test_complete_ai_pipeline_creates_grounded_entities_and_embeddings(db,monkeypatch):
    from app.ai import Extraction
    event=populate(db);db.commit()
    monkeypatch.setattr(pipeline,'Session',sessionmaker(db.bind,expire_on_commit=False))
    monkeypatch.setattr(settings,'ai_enabled',True)
    class LocalContract:
        async def extract(self,text):
            title=text.split('\n')[0]
            return Extraction(summary_quotes=[title],entities=[{'kind':'organization','name':'Улсын','quote':title}],claims=[],category='economy',confidence=.6)
        async def embed(self,text):return [1.0]+[0.0]*1023
    result=asyncio.run(pipeline.process_batch(LocalContract()))
    assert all(r['status']=='ai_complete' for r in result['items'])
    with sessionmaker(db.bind)() as check:
        assert check.scalar(select(func.count()).select_from(ArticleEmbedding))==2
        assert check.scalar(select(func.count()).select_from(EntityMention))==2
        assert check.scalar(select(func.count()).select_from(PublicReport).where(PublicReport.state=='published'))==0
    assert asyncio.run(pipeline.process_batch(LocalContract()))['items']==[]

def test_published_snapshot_survives_article_change(db):
    event=populate(db);report=build_report(db,event.id);report.state='published';db.commit()
    snapshot=report.body_hash;article=db.scalar(select(Article));s=db.get(Source,article.source_id)
    ingest(db,s,[{'title':'Өөр мэдээний шинэ гарчиг','excerpt':'Өөр шинэ агуулга','url':article.url,'published_at':None,'updated_at':None}]);rebuild_events(db);db.commit()
    assert db.get(PublicReport,report.id).body_hash==snapshot
    assert canonical_event(db,event.id) is not None

def test_expired_draft_cannot_be_published(client,db,monkeypatch):
    from app.operations import retain_versions
    event=populate(db);r=build_report(db,event.id);db.commit();auth=headers(monkeypatch)
    a=db.scalar(select(Article));v=db.scalar(select(ArticleVersion).where(ArticleVersion.article_id==a.id));v.observed_at=now()-timedelta(days=365)
    ingest(db,db.get(Source,a.source_id),[{'title':'Changed','excerpt':'Changed','url':a.url,'published_at':None,'updated_at':None}]);retain_versions(db,False);db.commit()
    result=client.post(f'/api/v1/admin/reports/{r.id}/review',headers=auth,json={'decision':'publish','privacy_checked':True,'finding':'needs_review','note':'All evidence checked by reviewer.','expected_hash':r.body_hash})
    assert result.status_code==409

def test_merged_event_ids_remain_resolvable(db):
    source=Source(name='Fixture',endpoint='https://ikon.mn/rss');db.add(source);db.flush()
    ingest(db,source,[{'url':'https://ikon.mn/a','title':'Нэг мэдээ','excerpt':'Төсвийн тухай','published_at':None,'updated_at':None},{'url':'https://ikon.mn/b','title':'Дэлхийн спорт','excerpt':'Спортын тухай','published_at':None,'updated_at':None}]);rebuild_events(db);db.flush()
    old_ids=list(db.scalars(select(Event.id).order_by(Event.id)))
    assert len(old_ids)==2
    ingest(db,source,[{'url':'https://ikon.mn/b','title':'Нэг мэдээ','excerpt':'Төсвийн тухай','published_at':None,'updated_at':None}]);rebuild_events(db);db.commit()
    assert canonical_event(db,old_ids[0]).id==canonical_event(db,old_ids[1]).id
    assert db.get(Event,old_ids[1]) is not None
