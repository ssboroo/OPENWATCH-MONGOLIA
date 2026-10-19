import asyncio
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import calendar
import ipaddress
import feedparser
from bs4 import BeautifulSoup
from defusedxml import ElementTree
from sqlalchemy import select, delete, text
from .models import Article, ArticleVersion, Source, Event, EventArticle, SimilarityMatch, CollectionRun, now
from .db import Session
from .config import settings
from .security import fetch_feed

def canonical(url):
    if len(url.encode('utf-8'))>2048:raise ValueError('Article URL exceeds size limit')
    u = urlsplit(url)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise ValueError('Invalid article URL')
    if u.hostname.lower() in ('localhost','localhost.localdomain') or u.hostname.lower().endswith('.local'):raise ValueError('Local article URL blocked')
    try:address=ipaddress.ip_address(u.hostname)
    except ValueError:address=None
    if address is not None and not address.is_global:raise ValueError('Private article URL blocked')
    if any(k.casefold() in {'api_key','apikey','access_token','password','secret','authorization','token','signature'} for k,_ in parse_qsl(u.query)):raise ValueError('Credential-bearing article URL rejected')
    query = [(k,v) for k,v in parse_qsl(u.query) if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid'}]
    return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path or '/', urlencode(sorted(query)), ''))

def clean(value):
    return ' '.join(BeautifulSoup(value, 'html.parser').get_text(' ').split())

def digest(title, excerpt):
    return hashlib.sha256(f'{title}\n{excerpt}'.encode()).hexdigest()

def similarity(a, b):
    x, y = set(re.findall(r'\w+', a.lower())), set(re.findall(r'\w+', b.lower()))
    return len(x & y) / len(x | y) if x and y else 0.0

def parse_feed(raw):
    ElementTree.fromstring(raw)  # Reject DTD/entity expansion before feedparser.
    feed = feedparser.parse(raw)
    if feed.bozo or not feed.version:
        raise ValueError('Invalid RSS/Atom feed')
    rows = []
    for e in feed.entries[:500]:
        if not e.get('link') or not e.get('title'):
            continue
        def timestamp(key):
            val = dict(e).get(key)
            raw_date=str(dict(e).get(key.removesuffix('_parsed'),''))
            if not re.search(r'(?:[+-]\d{2}:?\d{2}|Z|UTC|GMT|[ECMP][SD]T)\s*$',raw_date,re.I):return None
            return datetime.fromtimestamp(calendar.timegm(val), timezone.utc) if val else None
        rows.append(dict(url=canonical(e.link), title=clean(e.title)[:1000], excerpt=clean(e.get('summary',''))[:600], published_at=timestamp('published_parsed'), updated_at=timestamp('updated_parsed'),source_metadata={'published_raw':str(dict(e).get('published',''))[:200],'updated_raw':str(dict(e).get('updated',''))[:200]}))
    return rows

from .clustering import rebuild_events

def ingest(db, source, rows):
    added = 0
    for row in rows:
        h = digest(row['title'], row['excerpt'])
        a = db.scalar(select(Article).where(Article.url == row['url']))
        if a is None:
            a = Article(source_id=source.id, **row, text_hash=h, version=1, fetched_at=now())
            db.add(a); db.flush(); added += 1
        elif a.source_id != source.id:
            if a.source_metadata.get('metadata_only') and not row.get('source_metadata',{}).get('metadata_only'):
                from .catalog import domain_of
                if domain_of(a.url)!=domain_of(source.endpoint):continue
                a.source_id=source.id;a.version+=1
                for key,value in row.items():setattr(a,key,value)
                a.text_hash=h
            else:continue
        else:
            a.fetched_at = now()
            if a.text_hash == h:
                changed=False
                for key in ('published_at','updated_at'):
                    val=row.get(key)
                    from .clustering import utc
                    old=getattr(a,key)
                    if (utc(val) if val else None)!=(utc(old) if old else None):
                        setattr(a,key,val);changed=True
                if 'source_metadata' in row:a.source_metadata=row['source_metadata']
                if changed:a.analysis_hash=None;a.analysis_status='pending'
                continue
            a.version += 1
            for k,v in row.items():
                setattr(a, k, v)
            a.text_hash = h
        a.source_metadata=dict(row.get('source_metadata',{}))
        a.analysis_status='pending';a.analysis_hash=None;a.ai_hash=None;a.next_analysis_at=None
        db.add(ArticleVersion(article_id=a.id, source_id=source.id,source_metadata=dict(a.source_metadata or {}),version=a.version, title=a.title, excerpt=a.excerpt, text_hash=h))
    db.flush()
    return added

async def collect():
    with Session() as lockdb:
        if lockdb.bind.dialect.name == 'postgresql':
            if not lockdb.scalar(text('SELECT pg_try_advisory_lock(20471019)')):
                return {'status':'already_running'}
        run_id=None
        try:
            with Session() as db:
                run = CollectionRun(); db.add(run); db.commit(); run_id = run.id
                ids = list(db.scalars(select(Source.id).where(Source.active.is_(True))))
            added, errors = 0, []
            semaphore=asyncio.Semaphore(max(1,min(settings.collection_concurrency,8)))
            async def collect_one(sid):
                nonlocal added
                async with semaphore:
                    await collect_locked(sid)
            async def collect_locked(sid):
                nonlocal added
                with Session() as db:
                    source = db.get(Source, sid)
                    try:
                        source.checked_at = now()
                        from .importers import parse_source
                        rows = parse_source(await asyncio.wait_for(fetch_feed(source.endpoint),settings.source_timeout_seconds),source.kind,source.endpoint)
                        added += ingest(db, source, rows)
                        source.success_at = now(); source.error = None
                        db.commit()
                    except Exception as exc:
                        db.rollback()
                        source = db.get(Source, sid); source.checked_at = now(); source.error = type(exc).__name__ + ': ' + str(exc)[:300]
                        errors.append({'source_id':sid,'error':source.error}); db.commit()
                await asyncio.sleep(1)
            await asyncio.gather(*(collect_one(sid) for sid in ids))
            with Session() as db:
                rebuild_events(db)
                run = db.get(CollectionRun, run_id); run.finished_at = now(); run.status = 'partial' if errors else 'completed'; run.added = added; run.errors = errors
                db.commit()
            return {'status':'partial' if errors else 'completed','added':added,'errors':errors}
        except Exception as exc:
            try:
                with Session() as db:
                    run=db.get(CollectionRun,run_id) if run_id else None
                    if run:
                        run.status='failed';run.finished_at=now();run.errors=[{'stage':'collection','error':type(exc).__name__}];db.commit()
            except Exception:pass
            return {'status':'failed','error':type(exc).__name__}
        finally:
            if lockdb.bind.dialect.name == 'postgresql':
                lockdb.execute(text('SELECT pg_advisory_unlock(20471019)'))
