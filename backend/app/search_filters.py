"""Shared article scope; calendar dates are inclusive Ulaanbaatar days."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, func, or_, and_
from .models import Article, Source, ArticleBodyCheck, ArticleVersion
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


def advanced(stmt, db, q='', match='phrase', field='all', exclude='', analysis='', body='', publication=''):
    """Bounded literal search and current-version processing filters; no raw SQL."""
    from .body_checks import VERSION
    columns=[Article.title] if field=='title' else [Article.excerpt] if field=='excerpt' else [] if field=='body' else [Article.title,Article.excerpt]
    body_scope=select(ArticleBodyCheck.article_id).join(ArticleVersion,ArticleVersion.id==ArticleBodyCheck.article_version_id).where(ArticleBodyCheck.article_id==Article.id,ArticleVersion.version==Article.version,ArticleBodyCheck.state=='ready',ArticleBodyCheck.data['adapter'].as_string()==VERSION).correlate(Article)
    def contains(term):
        escaped=term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        clauses=[column.ilike('%'+escaped+'%',escape='\\') for column in columns]
        if field in ('all','body'):clauses.append(body_scope.where(ArticleBodyCheck.data['lead'].as_string().ilike('%'+escaped+'%',escape='\\')).exists())
        return or_(*clauses)
    words=list(dict.fromkeys(q.split()))
    omitted=list(dict.fromkeys(exclude.split()))
    if (match!='phrase' and len(words)>20) or len(omitted)>20:
        raise HTTPException(422,'Use at most 20 search words and 20 excluded words')
    if words:
        clauses=[contains(q.strip())] if match=='phrase' else [contains(word) for word in words]
        stmt=stmt.where(or_(*clauses) if match=='any' else and_(*clauses))
    for word in omitted:stmt=stmt.where(~contains(word))
    if analysis=='complete':stmt=stmt.where(Article.analysis_status=='ai_complete')
    elif analysis=='pending':stmt=stmt.where(Article.analysis_status.in_(['pending','metadata_only','lexical_only']))
    elif analysis=='unavailable':stmt=stmt.where(Article.analysis_status=='ai_unavailable')
    if publication=='known':stmt=stmt.where(Article.published_at.is_not(None))
    elif publication=='unknown':stmt=stmt.where(Article.published_at.is_(None))
    if body:
        ready=select(ArticleBodyCheck.article_id).join(ArticleVersion,ArticleVersion.id==ArticleBodyCheck.article_version_id).where(
            ArticleBodyCheck.article_id==Article.id,ArticleVersion.version==Article.version,
            ArticleBodyCheck.state=='ready',ArticleBodyCheck.data['adapter'].as_string()==VERSION).correlate(Article).exists()
        stmt=stmt.where(ready if body=='ready' else ~ready)
    return stmt


def fresh(stmt, db, freshness='all'):
    """Use publication, never discovery, as the freshness proof."""
    if freshness=='all':return stmt
    from .models import now
    current=now();cutoff=current-timedelta(hours=48 if freshness=='48h' else 168)
    if db.bind.dialect.name=='sqlite':current=current.replace(tzinfo=None);cutoff=cutoff.replace(tzinfo=None)
    return stmt.where(Article.published_at>=cutoff,Article.published_at<=current)

