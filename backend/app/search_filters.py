"""Shared article scope; calendar dates are inclusive Ulaanbaatar days."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, func
from .models import Article, Source
from .catalog import BY_DOMAIN, domain_of

SORTS = ('newest', 'oldest', 'published_newest', 'relevance')

def scope(stmt, db, domain='', source_id=None, date_from=None, date_to=None, date_field='published', category=''):
    if date_to==date.max:raise HTTPException(422,'End date is out of range')
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'Start date must be on or before end date')
    if domain and domain not in BY_DOMAIN:
        raise HTTPException(422, 'Unknown media domain')
    if domain or category:
        allowed={d for d,s in BY_DOMAIN.items() if (not domain or d==domain) and (not category or s['category']==category)}
        ids=[s.id for s in db.scalars(select(Source)) if domain_of(s.endpoint) in allowed]
        stmt=stmt.where(Article.source_id.in_(ids))
    if source_id is not None:stmt=stmt.where(Article.source_id==source_id)
    column=Article.published_at if date_field=='published' else Article.first_seen_at
    # Keep a missing publication date unknown instead of substituting discovery time.
    for day,upper in ((date_from,False),(date_to,True)):
        if day:
            boundary=datetime.combine(day,time.min,ZoneInfo('Asia/Ulaanbaatar')).astimezone(timezone.utc)
            if upper:boundary+=timedelta(days=1)
            if db.bind.dialect.name=='sqlite':boundary=boundary.replace(tzinfo=None)
            stmt=stmt.where(column<boundary if upper else column>=boundary)
    return stmt

def ordered(stmt, sort='newest'):
    if sort=='oldest':return stmt.order_by(Article.first_seen_at.asc(),Article.id.asc())
    if sort=='published_newest':return stmt.order_by(Article.published_at.desc().nullslast(),Article.id.desc())
    return stmt.order_by(Article.first_seen_at.desc(),Article.id.desc())
