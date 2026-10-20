import asyncio
from datetime import date
import hmac
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.responses import JSONResponse
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select, func, text, or_, literal_column
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DB
from .config import settings
from .db import get_db
from .models import Source, Article, ArticleVersion, Event, EventArticle, SimilarityMatch, CollectionRun, AuditLog, now
from .collector import collect, parse_feed
from .security import fetch_feed, resolve_public
from .catalog import BY_DOMAIN, SITES, directory, web_search_link, domain_of

@asynccontextmanager
async def lifespan(app):
    yield
    for task in list(tasks):
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(title='OpenWatch Mongolia', lifespan=lifespan)
from .http_limits import BodyLimit
app.add_middleware(BodyLimit)
tasks = set()
buckets = defaultdict(deque)
submission_buckets = defaultdict(deque)

@app.middleware('http')
async def limits(request: Request, call_next):
    key = request.client.host if request.client else 'unknown'
    t = time.monotonic()
    # Periodically discard idle clients to bound memory.
    for old in list(buckets):
        if not buckets[old] or buckets[old][-1] < t-60:
            del buckets[old]
    # Publisher assets have their own bounded budget; browsing logos cannot
    # exhaust article/search reads. Health probes do not consume either budget.
    asset = request.method in ('GET','HEAD') and request.url.path.startswith('/api/v1/source-icons/')
    if request.url.path != '/health':
        scope='icons' if asset else 'api'
        q = buckets[(key,scope)]
        while q and q[0] < t-60:
            q.popleft()
        if len(q) >= (600 if asset else 120):
            import math
            retry=max(1,math.ceil(q[0]+60-t))
            return JSONResponse({'detail':'Rate limit exceeded','scope':scope}, status_code=429, headers={'Retry-After':str(retry),'X-RateLimit-Scope':scope})
        q.append(t)
    if request.method=='POST' and request.url.path.endswith('/corrections'):
        for old in list(submission_buckets):
            if not submission_buckets[old] or submission_buckets[old][-1]<t-3600:del submission_buckets[old]
        history=submission_buckets[key]
        while history and history[0]<t-3600:history.popleft()
        if len(history)>=5:return JSONResponse({'detail':'Correction rate limit exceeded'},status_code=429,headers={'Retry-After':'3600'})
        history.append(t)
    response = await call_next(request)
    if request.url.path.startswith('/api/v1/admin/'):
        response.headers['Cache-Control']='no-store'
    response.headers['X-RateLimit-Scope'] = 'health' if request.url.path == '/health' else 'icons' if asset else 'api'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse({'detail':'Database unavailable'}, status_code=503)

def admin(authorization: str = Header(default='')):
    expected = f'Bearer {settings.admin_token}'
    if len(settings.admin_token) < 32 or settings.admin_token.startswith('CHANGE_ME') or not hmac.compare_digest(authorization.encode('utf-8'), expected.encode('utf-8')):
        raise HTTPException(401, 'Admin bearer token required')

class SourceInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    endpoint: HttpUrl
    kind: Literal['rss','atom','json','csv','sitemap','html'] = 'rss'
    publisher: str = Field(default='', max_length=200)
    license: str = Field(default='', max_length=2000)
    permission_note: str = Field(default='', max_length=2000)

class SourcePatch(BaseModel):
    active: bool | None = None
    license: str | None = Field(default=None, max_length=2000)
    permission_note: str | None = Field(default=None, max_length=2000)

def get_or_404(db, model, id):
    row = db.get(model, id)
    if row is None:
        raise HTTPException(404, 'Not found')
    return row

def page(db, statement, offset, limit):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    return {'items':list(db.scalars(statement.offset(offset).limit(limit))), 'total':total, 'offset':offset, 'limit':limit}

@app.get('/health')
def health(db: DB = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status':'ok','ai':'enabled' if settings.ai_enabled else 'not_enabled','collector':'separate_worker'}

@app.get('/api/v1/sources')
def sources(db: DB = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    return page(db, select(Source).order_by(Source.id), offset, limit)

@app.post('/api/v1/sources', dependencies=[Depends(admin)], status_code=201)
async def add_source(data: SourceInput, db: DB = Depends(get_db)):
    try:
        await resolve_public(str(data.endpoint))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if db.scalar(select(Source).where(Source.endpoint == str(data.endpoint))):
        raise HTTPException(409, 'Source already exists')
    row = Source(**data.model_dump(exclude={'endpoint'}), endpoint=str(data.endpoint), active=False)
    db.add(row); db.add(AuditLog(action='source.create', detail=row.endpoint)); db.commit(); db.refresh(row)
    return row

@app.post('/api/v1/sources/{id}/validate', dependencies=[Depends(admin)])
async def validate_source(id: int, db: DB = Depends(get_db)):
    source = get_or_404(db, Source, id)
    source.checked_at = now()
    try:
        from .importers import parse_source
        rows = parse_source(await fetch_feed(source.endpoint),source.kind,source.endpoint)
        source.validated_at = now(); source.error = None
        result = {'valid':True,'entries':len(rows)}
    except Exception as exc:
        source.validated_at = None; source.active = False; source.error = str(exc)[:300]
        result = {'valid':False,'error':source.error}
    db.add(AuditLog(action='source.validate', detail=str(id))); db.commit()
    return result

@app.patch('/api/v1/sources/{id}', dependencies=[Depends(admin)])
def patch_source(id: int, data: SourcePatch, db: DB = Depends(get_db)):
    source = get_or_404(db, Source, id)
    if data.license is not None:
        source.license = data.license.strip()
    if data.permission_note is not None:
        source.permission_note = data.permission_note.strip()
    will_be_active = data.active if data.active is not None else source.active
    if will_be_active and (not source.validated_at or not source.permission_note.strip() or not source.license.strip()):
        raise HTTPException(422, 'Validate feed and document license/permission before activation')
    source.active = will_be_active
    db.add(AuditLog(action='source.activate', detail=f'{id}:{data.active}')); db.commit()
    return source

@app.get('/api/v1/sources/{id}')
def source_detail(id: int, db: DB = Depends(get_db)):
    return get_or_404(db, Source, id)

@app.get('/api/v1/search')
@app.get('/api/v1/articles')
def articles(match: str = Query('phrase',pattern='^(phrase|all|any)$'), field: str = Query('all',pattern='^(all|title|excerpt|body)$'), exclude: str = Query('',max_length=200), analysis: str = Query('',pattern='^(|complete|pending|unavailable)$'), body: str = Query('',pattern='^(|ready|unread)$'), publication: str = Query('',pattern='^(|known|unknown)$'), q: str = Query('', max_length=200), mode: str = Query('lexical',pattern='^(lexical|fts)$'), domain: str = Query('', max_length=253), source_id: int | None = Query(None,gt=0), date_from: date | None = None, date_to: date | None = None, date_field: str = Query('published',pattern='^(published|discovered)$'), category: str = Query('',pattern='^(|news|regional|business|broadcast|official)$'), sort: str = Query('newest',pattern='^(newest|oldest|published_newest|relevance)$'), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), db: DB = Depends(get_db)):
    from .search_filters import scope, ordered, advanced
    q=q.strip()
    stmt = scope(select(Article),db,domain,source_id,date_from,date_to,date_field,category)
    indexed = bool(q and mode=='fts' and match=='phrase' and field=='all' and db.bind.dialect.name=='postgresql')
    stmt=advanced(stmt,db,q,match,field,exclude,analysis,body,publication)
    if indexed:
        doc=func.to_tsvector(literal_column("'simple'"),Article.title+literal_column("' '")+Article.excerpt)
        query=func.websearch_to_tsquery(literal_column("'simple'"),q)
        stmt=stmt.where(doc.op('@@')(query))
        if sort=='relevance':stmt=stmt.order_by(func.ts_rank_cd(doc,query).desc())
    result=page(db, ordered(stmt,sort), offset, limit)
    from .serialization import article_data
    result['items']=[article_data(a) for a in result['items']]
    result['mode']='fts' if indexed else 'lexical'
    result['sort']=sort if sort!='relevance' or indexed else 'newest'
    result['timezone']='Asia/Ulaanbaatar'
    result['filters']={'match':match,'field':field,'exclude':exclude,'analysis':analysis,'body':body,'publication':publication}
    result['limitation']='Сонгосон нөхцөлд үгийн хайлт ашиглав. Хайлт зөвхөн архивын гарчиг, хураангуйд хамаарна.' if mode=='fts' and not indexed and q else 'Архивын гарчиг, хураангуй болон уншсан эхийн хадгалсан эхний ≤600 тэмдэгтэд хайна. Бүтэн эхийн хайлт биш.'
    if indexed:result['limitation']='Индекст хайлт гарчиг, хураангуйд хамаарна. Уншсан эхийн эхлэлээс хайх бол үгийн хайлт сонгоно уу.'
    return result

@app.get('/api/v1/articles/{id}')
def article(id: int, db: DB = Depends(get_db)):
    from .serialization import article_data
    return article_data(get_or_404(db, Article, id))

@app.get('/api/v1/articles/{id}/versions')
def versions(id: int, db: DB = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    get_or_404(db, Article, id)
    result=page(db, select(ArticleVersion).where(ArticleVersion.article_id == id).order_by(ArticleVersion.version.desc()), offset, limit)
    from .evidence import redact
    result['items']=[{'id':v.id,'article_id':v.article_id,'source_id':v.source_id,'version':v.version,'title':redact(v.title),'excerpt':redact(v.excerpt),'text_hash':v.text_hash,'observed_at':v.observed_at} for v in result['items']]
    return result

@app.get('/api/v1/clusters')
@app.get('/api/v1/events')
def events(db: DB = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    return page(db, select(Event).where(Event.merged_into_id.is_(None)).order_by(Event.first_seen_at.desc(), Event.id.desc()), offset, limit)

@app.get('/api/v1/events/{id}')
def event_detail(id: int, db: DB = Depends(get_db)):
    from .clustering import canonical_event
    event=canonical_event(db,id)
    if event is None:raise HTTPException(404,'Not found')
    id=event.id
    return {'event':event, 'matches':list(db.scalars(select(SimilarityMatch).join(EventArticle, SimilarityMatch.article_id == EventArticle.article_id).where(EventArticle.event_id == id)))}

@app.get('/api/v1/events/{id}/timeline')
def timeline(id: int, db: DB = Depends(get_db)):
    from .clustering import canonical_event
    event=canonical_event(db,id)
    if event is None:raise HTTPException(404,'Not found')
    id=event.id
    rows = list(db.scalars(select(Article).join(EventArticle, Article.id == EventArticle.article_id).where(EventArticle.event_id == id).order_by(Article.published_at.asc().nulls_last(), Article.id)))
    from .serialization import article_data
    return {'items':[article_data(a) for a in rows],'timezone':'UTC','limitation':'Хамгийн эрт бүртгэгдсэн нийтлэл нь анхны нийтлэгч гэдгийг батлахгүй.'}

@app.get('/api/v1/events/{id}/sources')
def event_sources(id: int, db: DB = Depends(get_db)):
    from .clustering import canonical_event
    event=canonical_event(db,id)
    if event is None:raise HTTPException(404,'Not found')
    id=event.id
    return {'items':list(db.scalars(select(Source).join(Article).join(EventArticle, EventArticle.article_id == Article.id).where(EventArticle.event_id == id).distinct()))}

@app.get('/api/v1/statistics')
def statistics(db: DB = Depends(get_db)):
    result={name:db.scalar(select(func.count()).select_from(model)) for name,model in [('sources',Source),('articles',Article),('events',Event),('matches',SimilarityMatch)]}
    result['events']=db.scalar(select(func.count()).select_from(Event).where(Event.merged_into_id.is_(None)))
    return result

@app.get('/api/v1/collector/status')
def collector_status(db: DB = Depends(get_db)):
    return {'latest':db.scalar(select(CollectionRun).order_by(CollectionRun.id.desc()).limit(1)), 'interval_seconds':settings.collection_interval}

@app.post('/api/v1/collect/run', dependencies=[Depends(admin)], status_code=202)
async def run_collector(db: DB = Depends(get_db)):
    db.add(AuditLog(action='collect.request', detail='admin')); db.commit()
    task = asyncio.create_task(collect()); tasks.add(task); task.add_done_callback(tasks.discard)
    return {'status':'accepted','status_url':'/api/v1/collector/status'}

@app.get('/api/v1/media')
def media_directory(q: str = Query('', max_length=200), category: str = Query('', pattern='^(|news|regional|business|broadcast|official)$'), availability: str = Query('', pattern='^(|active|reachable|feed_found)$'), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: DB = Depends(get_db)):
    return directory(db, q, category, availability, offset, limit)

@app.get('/api/v1/media/options')
def media_options():
    return {'items':[{'domain':s['domain'],'name':s['name'],'category':s['category']} for s in SITES]}

@app.get('/api/v1/media/search')
def media_web_search(q: str = Query(..., min_length=1, max_length=200), domain: str = Query('', max_length=253), engine: str = Query('google', pattern='^(google|bing)$'), category: str = Query('',pattern='^(|news|regional|business|broadcast|official)$'), availability: str = Query('',pattern='^(|active|reachable|feed_found)$'), date_from: date | None = None, date_to: date | None = None, db: DB = Depends(get_db)):
    if not q.strip():
        raise HTTPException(422, 'Search query is required')
    if domain and domain not in BY_DOMAIN:
        raise HTTPException(422, 'Unknown media domain')
    if date_from and date_to and date_from>date_to:raise HTTPException(422,'Invalid date range')
    if engine=='bing' and (date_from or date_to):raise HTTPException(422,'Choose Google for date range links')
    selected=directory(db,category=category,availability=availability,limit=len(SITES))['items']
    sites = [s for s in selected if not domain or s['domain']==domain]
    groups = [sites[i:i+10] for i in range(0,len(sites),10)]
    return {'mode':'external_search_links','query':q,'engine':engine,'total_sites':len(sites),
        'groups':[{'domains':[s['domain'] for s in group], 'url':web_search_link(q,[s['domain'] for s in group],engine,date_from,date_to)} for group in groups],
        'items':[{'domain':s['domain'],'name':s['name'],'url':web_search_link(q,[s['domain']],engine,date_from,date_to)} for s in sites],
        'limitation':'Эдгээр нь хайлтын үр дүн биш, Google/Bing дээр хайх холбоосууд. Гаднын систем индексжүүлээгүй мэдээг харуулахгүй байж болно.'}


from .phase_api import install_routes
install_routes(app, admin, tasks)


@app.get('/metrics', include_in_schema=False)
def metrics(db: DB=Depends(get_db)):
    from fastapi.responses import PlainTextResponse
    import shutil
    from .models import SystemState,ReportCorrection
    from .clustering import utc
    disk=shutil.disk_usage('/')
    worker=db.get(SystemState,'worker')
    values={
        'openwatch_articles':db.scalar(select(func.count()).select_from(Article)),
        'openwatch_sources_active':db.scalar(select(func.count()).select_from(Source).where(Source.active.is_(True))),
        'openwatch_sources_error':db.scalar(select(func.count()).select_from(Source).where(Source.active.is_(True),Source.error.is_not(None))),
        'openwatch_worker_stale':int(worker is None or (now()-utc(worker.updated_at)).total_seconds()>600),
        'openwatch_disk_free_ratio':disk.free/disk.total,
        'openwatch_corrections_pending':db.scalar(select(func.count()).select_from(ReportCorrection).where(ReportCorrection.state=='pending')),
        'openwatch_ai_fallback_articles':db.scalar(select(func.count()).select_from(Article).where(Article.analysis_status=='ai_unavailable')),
    }
    return PlainTextResponse(''.join(f'# TYPE {name} gauge\n{name} {value}\n' for name,value in values.items()),media_type='text/plain; version=0.0.4')
