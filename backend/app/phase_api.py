"""Evidence, human review, corrections, graph, local semantic search and operations."""
import asyncio
from datetime import timedelta, date
from typing import Literal
import shutil
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select, func, or_, and_, text
from sqlalchemy.orm import Session as DB
from .db import get_db
from .config import settings
from .models import *
from .clustering import canonical_event, utc, publication_lock
from .ai import Ollama, InferenceFailure, cosine, PROMPT_VERSION
from .evidence import redact
from .reports import build_report, public_report, FINDINGS, content_hash
from .graph import evidence_graph
from .pipeline import process_batch, model_hash
from .catalog import BY_DOMAIN, domain_of

router=APIRouter(prefix='/api/v1')

def install_routes(app, admin, tasks):
    class BuildReport(BaseModel):
        event_id: int = Field(gt=0)
    class ReviewReport(BaseModel):
        decision: Literal['publish','withdraw','request_changes']
        expected_hash: str = Field(min_length=64,max_length=64)
        privacy_checked: bool = False
        finding: Literal['verified_sources','sources_differ','needs_review','insufficient_evidence','correction_received','unclear'] = 'needs_review'
        note: str = Field(min_length=10,max_length=3000)
    class CorrectionInput(BaseModel):
        text: str = Field(min_length=10,max_length=3000)
        evidence_urls: list[HttpUrl] = Field(default_factory=list,max_length=5)
    class CorrectionReview(BaseModel):
        decision: Literal['accepted','rejected']
        response: str = Field(min_length=10,max_length=3000)
        privacy_checked: bool = False

    @router.get('/research')
    def investigate(q:str=Query(...,min_length=1,max_length=200),domain:str=Query('',max_length=253),category:str=Query('',pattern='^(|news|regional|business|broadcast|official)$'),date_from:date|None=None,date_to:date|None=None,date_field:str=Query('discovered',pattern='^(published|discovered)$'),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=50),db:DB=Depends(get_db)):
        from .research import research
        return research(db,q,domain,category,date_from,date_to,date_field,offset,limit)

    @router.get('/reports')
    def list_reports(offset: int=Query(0,ge=0),limit: int=Query(20,ge=1,le=100),db: DB=Depends(get_db)):
        condition=PublicReport.state.in_(['published','withdrawn'])
        rows=list(db.scalars(select(PublicReport).where(condition).order_by(PublicReport.id.desc()).offset(offset).limit(limit)))
        return {'items':[{'id':r.id,'event_id':r.event_id,'title':redact(r.title),'revision':r.revision,'state':r.state,'finding':r.finding,'created_at':r.created_at,'reviewed_at':r.reviewed_at,'correction_pending':r.correction_pending} for r in rows],'total':db.scalar(select(func.count()).select_from(PublicReport).where(condition)),'offset':offset,'limit':limit}

    @router.get('/reports/{id}')
    def report(id:int,db:DB=Depends(get_db)):
        r=db.get(PublicReport,id)
        if r is None or r.state not in ('published','withdrawn'):raise HTTPException(404,'Published report not found')
        if r.state=='withdrawn':
            return {'id':r.id,'state':'withdrawn','title':redact(r.title),'review_note':redact(r.review_note or ''),'reviewed_at':r.reviewed_at,'body_hash':r.body_hash,'body':None}
        return public_report(db,r)

    @router.post('/reports/{id}/corrections',status_code=201)
    def submit_correction(id:int,data:CorrectionInput,db:DB=Depends(get_db)):
        r=db.get(PublicReport,id)
        if r is None or r.state!='published':raise HTTPException(404,'Published report not found')
        # Public submissions are never published automatically, and no private contact is collected.
        c=ReportCorrection(report_id=id,text=data.text,evidence_urls=[str(u) for u in data.evidence_urls]);db.add(c)
        r.correction_pending=True;db.commit();db.refresh(c)
        return {'id':c.id,'state':'pending','message':'Залруулгыг хүний хяналтад хүлээн авлаа. Нийтэд автоматаар нийтлээгүй.'}

    @router.get('/admin/reports',dependencies=[Depends(admin)])
    def admin_reports(state:str=Query('',pattern='^(|draft|published|withdrawn|changes_requested)$'),offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),db:DB=Depends(get_db)):
        q=select(PublicReport)
        if state:q=q.where(PublicReport.state==state)
        total=db.scalar(select(func.count()).select_from(q.subquery()))
        return {'items':list(db.scalars(q.order_by(PublicReport.id.desc()).offset(offset).limit(limit))),'total':total,'offset':offset,'limit':limit}

    @router.post('/admin/reports/build',dependencies=[Depends(admin)],status_code=201)
    def build(data:BuildReport,db:DB=Depends(get_db)):
        try:r=build_report(db,data.event_id)
        except ValueError as exc:raise HTTPException(422,str(exc))
        db.add(AuditLog(action='report.build',detail=str(r.id)));db.commit();return r

    @router.post('/admin/reports/{id}/review',dependencies=[Depends(admin)])
    def review(id:int,data:ReviewReport,db:DB=Depends(get_db)):
        publication_lock(db)
        r=db.scalar(select(PublicReport).where(PublicReport.id==id).with_for_update())
        if r is None:raise HTTPException(404,'Report not found')
        if r.body_hash!=data.expected_hash:raise HTTPException(409,'Report snapshot changed; reload before review')
        if data.decision=='publish':
            if r.state not in ('draft','changes_requested'):raise HTTPException(409,'Only a draft can be published; create a new revision')
            if not data.privacy_checked:raise HTTPException(422,'Explicit human privacy review required')
            if not r.body.get('evidence') or not r.body.get('articles'):raise HTTPException(422,'Source evidence required')
            if content_hash(r.body)!=r.body_hash:raise HTTPException(409,'Snapshot integrity check failed')
            vids=set(r.body.get('scope',{}).get('article_version_ids',[]))
            count=db.scalar(select(func.count()).select_from(ArticleVersion).where(ArticleVersion.id.in_(vids)))
            if not vids or count!=len(vids):raise HTTPException(409,'Evidence versions expired; rebuild a current draft')
            r.state='published';r.privacy_checked=True;r.finding=data.finding
        elif data.decision=='withdraw':
            if r.state!='published':raise HTTPException(409,'Only published reports can be withdrawn')
            r.state='withdrawn'
        else:
            if r.state not in ('draft','changes_requested'):raise HTTPException(409,'Published snapshots cannot be edited')
            r.state='changes_requested'
        r.review_note=data.note;r.reviewed_at=now()
        db.add(AuditLog(action='report.'+data.decision,detail=f'{id}:{r.body_hash}:{data.note}'));db.commit()
        return {'id':r.id,'state':r.state,'body_hash':r.body_hash}

    @router.get('/admin/corrections',dependencies=[Depends(admin)])
    def corrections(state:str=Query('pending',pattern='^(pending|accepted|rejected)$'),offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),db:DB=Depends(get_db)):
        return {'items':list(db.scalars(select(ReportCorrection).where(ReportCorrection.state==state).order_by(ReportCorrection.id).offset(offset).limit(limit))),'offset':offset,'limit':limit}

    @router.post('/admin/corrections/{id}/review',dependencies=[Depends(admin)])
    def review_correction(id:int,data:CorrectionReview,db:DB=Depends(get_db)):
        c=db.scalar(select(ReportCorrection).where(ReportCorrection.id==id).with_for_update())
        if c is None:raise HTTPException(404,'Correction not found')
        if c.state!='pending':raise HTTPException(409,'Correction already reviewed')
        if data.decision=='accepted' and not data.privacy_checked:raise HTTPException(422,'Privacy review required before public annotation')
        c.state=data.decision;c.response=data.response;c.reviewed_at=now();db.flush()
        r=db.scalar(select(PublicReport).where(PublicReport.id==c.report_id).with_for_update())
        r.correction_pending=bool(db.scalar(select(func.count()).select_from(ReportCorrection).where(ReportCorrection.report_id==r.id,ReportCorrection.state=='pending')))
        db.add(AuditLog(action='correction.'+data.decision,detail=f'{id}:{data.response}'));db.commit()
        return {'id':c.id,'state':c.state}

    @router.get('/events/{id}/graph')
    def graph(id:int,db:DB=Depends(get_db)):
        try:return evidence_graph(db,id)
        except ValueError as exc:raise HTTPException(404,str(exc))

    @router.get('/articles/{id}/analysis')
    def analysis(id:int,db:DB=Depends(get_db)):
        article=db.get(Article,id)
        if article is None:raise HTTPException(404,'Article not found')
        version=db.scalar(select(ArticleVersion).where(ArticleVersion.article_id==id,ArticleVersion.version==article.version))
        runs=list(db.scalars(select(AnalysisRun).where(AnalysisRun.article_id==id,AnalysisRun.article_version_id==version.id).order_by(AnalysisRun.id.desc()).limit(20))) if version else []
        from .connections import connections
        linked=connections(db,article)
        pending=settings.ai_enabled and article.ai_hash!=model_hash(article)
        if settings.ai_enabled:runs=[r for r in runs if r.model==settings.ollama_model and r.prompt_version==PROMPT_VERSION]
        status='awaiting_ai' if pending and article.analysis_status in ('metadata_only','lexical_only','pending') else article.analysis_status
        return {'article_id':id,'ai_enabled':settings.ai_enabled,'ai_pending':pending,'status':status,'connections':linked,'items':[{'model':r.model,'prompt_version':r.prompt_version,'status':r.status,'source_article_ids':[id],'evidence_urls':r.evidence_urls,'confidence':r.confidence,'limitation':r.limitation,'created_at':r.created_at,'scope':r.result.get('scope'),'summary_quotes':[redact(q) for q in r.result.get('summary_quotes',[])]} for r in runs]}

    @router.get('/comparison/groups')
    def grouped_comparison(q:str=Query('',max_length=200),domain:str=Query('',max_length=253),kind:str=Query('all',pattern='^(all|exact|cross_site)$'),sort:str=Query('newest',pattern='^(newest|largest)$'),offset:int=Query(0,ge=0),limit:int=Query(12,ge=1,le=30),db:DB=Depends(get_db)):
        from .comparison_index import comparison_groups
        return comparison_groups(db,q,domain,kind,offset,limit,sort)

    @router.get('/comparison/status')
    def comparison_status(db:DB=Depends(get_db)):
        from .body_checks import coverage
        return coverage(db)

    @router.get('/articles/{id}/comparison')
    def comparison(id:int,other_id:int|None=Query(None,gt=0),db:DB=Depends(get_db)):
        article=db.get(Article,id)
        if article is None:raise HTTPException(404,'Article not found')
        if other_id is not None and (other_id==id or db.get(Article,other_id) is None):raise HTTPException(422,'Choose two distinct existing articles')
        from .body_checks import compare_archive,JOBS
        return {**compare_archive(db,article,other_id),'running':id in JOBS}

    body_requests={}
    @router.post('/articles/{id}/content-check',status_code=202)
    async def request_content_check(id:int,request:Request,db:DB=Depends(get_db)):
        import time
        from .body_checks import JOBS,check_with_neighbors
        if db.get(Article,id) is None:raise HTTPException(404,'Article not found')
        if id in JOBS:return {'status':'already_running'}
        if len(JOBS)>=2:raise HTTPException(429,'Body analysis busy; retry shortly')
        key=request.client.host if request.client else 'unknown';current=time.monotonic()
        # Bound both memory and publisher reads for this fixed-article-ID endpoint.
        for old in list(body_requests):
            body_requests[old]=[t for t in body_requests[old] if current-t<60]
            if not body_requests[old]:del body_requests[old]
        history=body_requests.setdefault(key,[])
        if len(history)>=3:raise HTTPException(429,'Three body checks per minute; retry shortly')
        history.append(current);JOBS.add(id)
        task=asyncio.create_task(check_with_neighbors(id));tasks.add(task);task.add_done_callback(tasks.discard)
        return {'status':'accepted','status_url':f'/api/v1/articles/{id}/comparison'}

    @router.get('/articles/{id}/connections')
    def related_articles(id:int,db:DB=Depends(get_db)):
        article=db.get(Article,id)
        if article is None:raise HTTPException(404,'Article not found')
        from .connections import connections
        return connections(db,article)

    @router.post('/admin/analysis/run',dependencies=[Depends(admin)],status_code=202)
    async def run_analysis():
        task=asyncio.create_task(process_batch());tasks.add(task);task.add_done_callback(tasks.discard)
        return {'status':'accepted','status_url':'/api/v1/system/status'}

    @router.get('/semantic-search')
    async def semantic_search(q:str=Query(...,min_length=1,max_length=200),domain:str=Query('',max_length=253),source_id:int|None=Query(None,gt=0),date_from:date|None=None,date_to:date|None=None,date_field:str=Query('published',pattern='^(published|discovered)$'),category:str=Query('',pattern='^(|news|regional|business|broadcast|official)$'),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),db:DB=Depends(get_db)):
        if not q.strip():raise HTTPException(422,'Query is required')
        from .search_filters import scope
        # Validate even when the local AI is unavailable.
        scope(select(Article),db,domain,source_id,date_from,date_to,date_field,category)
        try:
            if not settings.ai_enabled:raise InferenceFailure('Local AI is disabled')
            vector=await Ollama().embed(q)
            stmt=select(ArticleEmbedding,Article).join(Article,Article.id==ArticleEmbedding.article_id).where(ArticleEmbedding.model==settings.embedding_model,ArticleEmbedding.text_hash==Article.text_hash)
            stmt=scope(stmt,db,domain,source_id,date_from,date_to,date_field,category)
            if db.bind.dialect.name=='postgresql':
                distance=ArticleEmbedding.vector.cosine_distance(vector)
                stmt=stmt.where(distance<.6).order_by(distance).limit(1100)
            else:stmt=stmt.order_by(Article.id.desc()).limit(2000)
            ranked=sorted([(cosine(e.vector,vector),a) for e,a in db.execute(stmt)],key=lambda pair:pair[0],reverse=True)
            ranked=[(score,a) for score,a in ranked if score>=.4]
            from .serialization import article_data
            return {'mode':'semantic','model':settings.embedding_model,'items':[{**article_data(a),'similarity':round(score,4)} for score,a in ranked[offset:offset+limit]],'total':len(ranked),'offset':offset,'limit':limit,'candidate_limit':1100 if db.bind.dialect.name=='postgresql' else 2000,'limitation':'Тоо нь хязгаарласан нэр дэвшигчдийн хүрээний тоо. Утгын ойролцоо байдал нь үнэн зөвийн оноо биш. Нийтэд татагдсан, embedding үүссэн нийтлэлээр хязгаарлана.'}
        except InferenceFailure:
            # Preserve usable search while explicitly labeling the lexical fallback.
            escaped=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            stmt=select(Article).where(or_(Article.title.ilike('%'+escaped+'%',escape='\\'),Article.excerpt.ilike('%'+escaped+'%',escape='\\')))
            stmt=scope(stmt,db,domain,source_id,date_from,date_to,date_field,category)
            total=db.scalar(select(func.count()).select_from(stmt.subquery()))
            from .serialization import article_data
            return {'mode':'lexical_fallback','items':[article_data(a) for a in db.scalars(stmt.order_by(Article.id.desc()).offset(offset).limit(limit))],'total':total,'offset':offset,'limit':limit,'limitation':'Локал AI байхгүй эсвэл алдаатай тул үгийн хайлт ашиглав.'}

    @router.get('/system/status')
    def system_status(db:DB=Depends(get_db)):
        states=list(db.scalars(select(SystemState).where(~SystemState.name.like('discovery:%'))))
        disk=shutil.disk_usage('/')
        worker=db.get(SystemState,'worker')
        stale=worker is None or (now()-utc(worker.updated_at)).total_seconds()>max(600,settings.worker_tick_seconds*5)
        return {'worker_stale':stale,'ai_enabled':settings.ai_enabled,'generation_model':settings.ollama_model,'embedding_model':settings.embedding_model,'disk_free_ratio':round(disk.free/disk.total,4),'disk_alert':disk.free/disk.total<.15,'states':[{'name':s.name,'value':{k:v for k,v in s.value.items() if k in ('status','processed','reports','enabled','batch_size','total')},'updated_at':s.updated_at} for s in states],'analysis_counts':dict(db.execute(select(Article.analysis_status,func.count()).group_by(Article.analysis_status)).all()),'ai_completed_articles':db.scalar(select(func.count()).select_from(Article).where(Article.analysis_status=='ai_complete')),'current_embeddings':db.scalar(select(func.count()).select_from(ArticleEmbedding).join(Article,Article.id==ArticleEmbedding.article_id).where(ArticleEmbedding.text_hash==Article.text_hash,ArticleEmbedding.model==settings.embedding_model)),'pending_corrections':db.scalar(select(func.count()).select_from(ReportCorrection).where(ReportCorrection.state=='pending'))}

    @router.get('/admin/audit',dependencies=[Depends(admin)])
    def audits(offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),db:DB=Depends(get_db)):
        return {'items':list(db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).offset(offset).limit(limit)))}

    @router.get('/admin/ai/status',dependencies=[Depends(admin)])
    async def ai_status():
        import httpx
        try:
            async with httpx.AsyncClient(base_url=settings.ollama_url,timeout=5,trust_env=False) as client:
                r=await client.get('/api/tags');r.raise_for_status()
            return {'enabled':settings.ai_enabled,'reachable':True,'models':[m.get('name') for m in r.json().get('models',[])]}
        except (httpx.HTTPError,ValueError):return {'enabled':settings.ai_enabled,'reachable':False,'models':[]}


    class RetentionInput(BaseModel):
        dry_run: bool = True

    @router.post('/admin/maintenance/retention',dependencies=[Depends(admin)])
    def retention(data:RetentionInput,db:DB=Depends(get_db)):
        from .operations import retain_versions
        result=retain_versions(db,data.dry_run);db.commit();return result

    @router.post('/admin/articles/{id}/check',dependencies=[Depends(admin)])
    async def availability(id:int,db:DB=Depends(get_db)):
        from .operations import observe_article
        try:result=await observe_article(db,id)
        except ValueError as exc:raise HTTPException(404,str(exc))
        db.add(AuditLog(action='article.check',detail=str(id)));db.commit();return result

    @router.get('/articles/{id}/observations')
    def observations(id:int,db:DB=Depends(get_db),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100)):
        if db.get(Article,id) is None:raise HTTPException(404,'Article not found')
        return {'items':list(db.scalars(select(ArticleObservation).where(ArticleObservation.article_id==id).order_by(ArticleObservation.id.desc()).offset(offset).limit(limit)))}


    class CatalogSyncInput(BaseModel):
        domain: str | None = Field(default=None,max_length=253)
    catalog_running=False

    @router.post('/admin/catalog/sync',dependencies=[Depends(admin)],status_code=202)
    async def sync_catalog(data:CatalogSyncInput):
        nonlocal catalog_running
        if data.domain and data.domain not in BY_DOMAIN:raise HTTPException(422,'Unknown media domain')
        if catalog_running:raise HTTPException(409,'Catalog scan already running')
        catalog_running=True
        async def execute():
            nonlocal catalog_running
            from .catalog_sync import sync
            from .pipeline import heartbeat
            from .db import Session
            try:
                with Session() as db:
                    heartbeat(db,'catalog',{'status':'running'});db.commit()
                result=await sync(data.domain)
                with Session() as db:
                    heartbeat(db,'catalog',{'status':'completed','processed':len(result)});db.commit()
            finally:catalog_running=False
        task=asyncio.create_task(execute());tasks.add(task);task.add_done_callback(tasks.discard)
        return {'status':'accepted','domain':data.domain,'status_url':'/api/v1/system/status'}

    app.include_router(router)
