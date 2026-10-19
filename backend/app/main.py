import asyncio
import hmac
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select, func, text, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DB
from .config import settings
from .db import get_db
from .models import Source, Article, ArticleVersion, Event, EventArticle, SimilarityMatch, CollectionRun, AuditLog, now
from .collector import collect, parse_feed
from .security import fetch_feed, resolve_public

@asynccontextmanager
async def lifespan(app):
    yield
    for task in list(tasks):
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(title='OpenWatch Mongolia', lifespan=lifespan)
tasks = set()
buckets = defaultdict(deque)

@app.middleware('http')
async def limits(request: Request, call_next):
    key = request.client.host if request.client else 'unknown'
    t = time.monotonic()
    # Periodically discard idle clients to bound memory.
    for old in list(buckets):
        if not buckets[old] or buckets[old][-1] < t-60:
            del buckets[old]
    q = buckets[key]
    while q and q[0] < t-60:
        q.popleft()
    if len(q) >= 120:
        return JSONResponse({'detail':'Rate limit exceeded'}, status_code=429, headers={'Retry-After':'60'})
    q.append(t)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse({'detail':'Database unavailable'}, status_code=503)

def admin(authorization: str = Header(default='')):
    expected = f'Bearer {settings.admin_token}'
    if len(settings.admin_token) < 32 or not hmac.compare_digest(authorization, expected):
        raise HTTPException(401, 'Admin bearer token required')

class SourceInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    endpoint: HttpUrl
    publisher: str = Field(default='', max_length=200)
    license: str = Field(default='', max_length=2000)
    permission_note: str = Field(default='', max_length=2000)

class SourcePatch(BaseModel):
    active: bool

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
    return {'status':'ok','ai':'not_enabled','collector':'separate_worker'}

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
        rows = parse_feed(await fetch_feed(source.endpoint))
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
    if data.active and (not source.validated_at or not source.permission_note or not source.license):
        raise HTTPException(422, 'Validate feed and document license/permission before activation')
    source.active = data.active
    db.add(AuditLog(action='source.activate', detail=f'{id}:{data.active}')); db.commit()
    return source

@app.get('/api/v1/sources/{id}')
def source_detail(id: int, db: DB = Depends(get_db)):
    return get_or_404(db, Source, id)

@app.get('/api/v1/search')
@app.get('/api/v1/articles')
def articles(q: str = Query('', max_length=200), source_id: int | None = None, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), db: DB = Depends(get_db)):
    stmt = select(Article)
    if q:
        escaped = q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        stmt = stmt.where(or_(Article.title.ilike(f'%{escaped}%', escape='\\'), Article.excerpt.ilike(f'%{escaped}%', escape='\\')))
    if source_id:
        stmt = stmt.where(Article.source_id == source_id)
    return page(db, stmt.order_by(Article.first_seen_at.desc(), Article.id.desc()), offset, limit)

@app.get('/api/v1/articles/{id}')
def article(id: int, db: DB = Depends(get_db)):
    return get_or_404(db, Article, id)

@app.get('/api/v1/articles/{id}/versions')
def versions(id: int, db: DB = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    get_or_404(db, Article, id)
    return page(db, select(ArticleVersion).where(ArticleVersion.article_id == id).order_by(ArticleVersion.version.desc()), offset, limit)

@app.get('/api/v1/clusters')
@app.get('/api/v1/events')
def events(db: DB = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    return page(db, select(Event).order_by(Event.first_seen_at.desc(), Event.id.desc()), offset, limit)

@app.get('/api/v1/events/{id}')
def event_detail(id: int, db: DB = Depends(get_db)):
    return {'event':get_or_404(db, Event, id), 'matches':list(db.scalars(select(SimilarityMatch).join(EventArticle, SimilarityMatch.article_id == EventArticle.article_id).where(EventArticle.event_id == id)))}

@app.get('/api/v1/events/{id}/timeline')
def timeline(id: int, db: DB = Depends(get_db)):
    get_or_404(db, Event, id)
    rows = list(db.scalars(select(Article).join(EventArticle, Article.id == EventArticle.article_id).where(EventArticle.event_id == id).order_by(Article.published_at.asc().nulls_last(), Article.id)))
    return {'items':rows,'timezone':'UTC','limitation':'Хамгийн эрт бүртгэгдсэн нийтлэл нь анхны нийтлэгч гэдгийг батлахгүй.'}

@app.get('/api/v1/events/{id}/sources')
def event_sources(id: int, db: DB = Depends(get_db)):
    get_or_404(db, Event, id)
    return {'items':list(db.scalars(select(Source).join(Article).join(EventArticle, EventArticle.article_id == Article.id).where(EventArticle.event_id == id).distinct()))}

@app.get('/api/v1/statistics')
def statistics(db: DB = Depends(get_db)):
    return {name:db.scalar(select(func.count()).select_from(model)) for name,model in [('sources',Source),('articles',Article),('events',Event),('matches',SimilarityMatch)]}

@app.get('/api/v1/collector/status')
def collector_status(db: DB = Depends(get_db)):
    return {'latest':db.scalar(select(CollectionRun).order_by(CollectionRun.id.desc()).limit(1)), 'interval_seconds':settings.collection_interval}

@app.post('/api/v1/collect/run', dependencies=[Depends(admin)], status_code=202)
async def run_collector(db: DB = Depends(get_db)):
    db.add(AuditLog(action='collect.request', detail='admin')); db.commit()
    task = asyncio.create_task(collect()); tasks.add(task); task.add_done_callback(tasks.discard)
    return {'status':'accepted','status_url':'/api/v1/collector/status'}

@app.get('/api/v1/reports')
def reports():
    return {'items':[], 'total':0, 'status':'Phase 3: хүний хяналттай тайлан хараахан идэвхжээгүй'}
