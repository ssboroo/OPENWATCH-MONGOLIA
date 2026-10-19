import asyncio
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import calendar
import feedparser
from bs4 import BeautifulSoup
from defusedxml import ElementTree
from sqlalchemy import select, delete, text
from .models import Article, ArticleVersion, Source, Event, EventArticle, SimilarityMatch, CollectionRun, now
from .db import Session
from .security import fetch_feed

def canonical(url):
    u = urlsplit(url)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise ValueError('Invalid article URL')
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
            return datetime.fromtimestamp(calendar.timegm(val), timezone.utc) if val else None
        rows.append(dict(url=canonical(e.link), title=clean(e.title)[:1000], excerpt=clean(e.get('summary',''))[:600], published_at=timestamp('published_parsed'), updated_at=timestamp('updated_parsed')))
    return rows

def rebuild_events(db):
    # Rebuild current lexical clusters transactionally; versions remain immutable.
    db.execute(delete(SimilarityMatch)); db.execute(delete(EventArticle)); db.execute(delete(Event))
    rows = list(db.scalars(select(Article).order_by(Article.id)))
    parent = {a.id: a.id for a in rows}
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, a in enumerate(rows):
        for b in rows[:i]:
            score = 1.0 if a.text_hash == b.text_hash else similarity(a.title+' '+a.excerpt, b.title+' '+b.excerpt)
            if score >= .72:
                parent[root(a.id)] = root(b.id)
                db.add(SimilarityMatch(article_id=a.id, other_id=b.id, score=score, method='sha256' if a.text_hash == b.text_hash else 'token_jaccard'))
    groups = {}
    for a in rows:
        groups.setdefault(root(a.id), []).append(a)
    for members in groups.values():
        event = Event(title=members[0].title, first_seen_at=min(a.first_seen_at for a in members))
        db.add(event); db.flush()
        db.add_all(EventArticle(event_id=event.id, article_id=a.id) for a in members)

def ingest(db, source, rows):
    added = 0
    for row in rows:
        h = digest(row['title'], row['excerpt'])
        a = db.scalar(select(Article).where(Article.url == row['url']))
        if a is None:
            a = Article(source_id=source.id, **row, text_hash=h, version=1, fetched_at=now())
            db.add(a); db.flush(); added += 1
        elif a.source_id != source.id:
            continue
        else:
            a.fetched_at = now()
            if a.text_hash == h:
                continue
            a.version += 1
            for k,v in row.items():
                setattr(a, k, v)
            a.text_hash = h
        db.add(ArticleVersion(article_id=a.id, version=a.version, title=a.title, excerpt=a.excerpt, text_hash=h))
    db.flush()
    return added

async def collect():
    with Session() as lockdb:
        if lockdb.bind.dialect.name == 'postgresql':
            if not lockdb.scalar(text('SELECT pg_try_advisory_lock(20471019)')):
                return {'status':'already_running'}
        try:
            with Session() as db:
                run = CollectionRun(); db.add(run); db.commit(); run_id = run.id
                ids = list(db.scalars(select(Source.id).where(Source.active.is_(True))))
            added, errors = 0, []
            for sid in ids:
                with Session() as db:
                    source = db.get(Source, sid)
                    try:
                        source.checked_at = now()
                        rows = parse_feed(await fetch_feed(source.endpoint))
                        added += ingest(db, source, rows)
                        source.success_at = now(); source.error = None
                        db.commit()
                    except Exception as exc:
                        db.rollback()
                        source = db.get(Source, sid); source.checked_at = now(); source.error = type(exc).__name__ + ': ' + str(exc)[:300]
                        errors.append({'source_id':sid,'error':source.error}); db.commit()
                await asyncio.sleep(1)
            with Session() as db:
                rebuild_events(db)
                run = db.get(CollectionRun, run_id); run.finished_at = now(); run.status = 'partial' if errors else 'completed'; run.added = added; run.errors = errors
                db.commit()
            return {'status':'partial' if errors else 'completed','added':added,'errors':errors}
        finally:
            if lockdb.bind.dialect.name == 'postgresql':
                lockdb.execute(text('SELECT pg_advisory_unlock(20471019)'))
