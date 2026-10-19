"""Stable event identifiers with bounded lexical candidates and exact hash groups.
Merged IDs remain resolvable; existing reports retain immutable snapshots.
"""
from collections import defaultdict, Counter
from datetime import timezone
import re
from sqlalchemy import select, delete, text
from .models import Article, ArticleEmbedding, Event, EventArticle, SimilarityMatch, now
from .config import settings
from .ai import cosine

def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def tokens(a):
    return set(re.findall(r'\w+', (a.title+' '+a.excerpt).casefold()))

def publication_lock(db):
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(20471021)'))

def rebuild_events(db):
    publication_lock(db)
    rows=list(db.scalars(select(Article).order_by(Article.id)))
    if not rows:return
    old={link.article_id:link.event_id for link in db.scalars(select(EventArticle))}
    existing={e.id:e for e in db.scalars(select(Event))}
    parent={a.id:a.id for a in rows}
    def root(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b):parent[root(a)]=root(b)
    sets={a.id:tokens(a) for a in rows}
    by_hash={}; inverted=defaultdict(list); pairs={}
    for a in rows:
        if a.text_hash in by_hash:
            b=by_hash[a.text_hash];union(a.id,b)
            pairs[(min(a.id,b),max(a.id,b))]=(1.0,'sha256')
        else:by_hash[a.text_hash]=a.id
        counts=Counter()
        # Rare tokens first; cap posting traversal and candidate comparisons.
        for token in sorted(sets[a.id],key=lambda t:len(inverted[t]))[:30]:
            counts.update(inverted[token][-settings.cluster_candidates:])
        for b_id,_ in counts.most_common(settings.cluster_candidates):
            other=sets[b_id];score=len(sets[a.id]&other)/len(sets[a.id]|other) if other else 0
            if score>=.72:
                union(a.id,b_id)
                key=(min(a.id,b_id),max(a.id,b_id))
                pairs.setdefault(key,(score,'token_jaccard'))
        for token in sets[a.id]:inverted[token].append(a.id)
    # A semantic edge is valid only for embeddings of the current text/model.
    valid_embeddings={e.article_id:e for e in db.scalars(select(ArticleEmbedding))}
    by_id={a.id:a for a in rows}
    for match in db.scalars(select(SimilarityMatch).where(SimilarityMatch.method=='embedding_cosine')):
        a,b=valid_embeddings.get(match.article_id),valid_embeddings.get(match.other_id)
        if a and b and a.model==b.model==settings.embedding_model and a.text_hash==by_id[a.article_id].text_hash and b.text_hash==by_id[b.article_id].text_hash:
            score=cosine(a.vector,b.vector)
            if score>=settings.semantic_threshold:
                union(a.article_id,b.article_id)
                pairs.setdefault((min(a.article_id,b.article_id),max(a.article_id,b.article_id)),(score,'embedding_cosine'))
    groups=defaultdict(list)
    for a in rows:groups[root(a.id)].append(a)
    db.execute(delete(SimilarityMatch));db.execute(delete(EventArticle));db.flush()
    used=set();assigned={}
    for members in sorted(groups.values(),key=lambda group:min(a.id for a in group)):
        candidates=sorted({old[a.id] for a in members if a.id in old and old[a.id] not in used and existing[old[a.id]].merged_into_id is None})
        event=existing[candidates[0]] if candidates else Event(title=members[0].title,first_seen_at=min(utc(a.first_seen_at) for a in members))
        event.title=members[0].title;event.updated_at=now();event.merged_into_id=None
        db.add(event);db.flush();used.add(event.id)
        for a in members:
            assigned[a.id]=event.id
            db.add(EventArticle(event_id=event.id,article_id=a.id))
    for eid,event in existing.items():
        if eid not in used:
            destinations={assigned[a] for a,e in old.items() if e==eid and a in assigned}
            if destinations:event.merged_into_id=min(destinations)
    for (a,b),(score,method) in pairs.items():
        db.add(SimilarityMatch(article_id=a,other_id=b,score=score,method=method))
    db.flush()

def canonical_event(db,event_id):
    visited=set()
    while event_id not in visited:
        visited.add(event_id);event=db.get(Event,event_id)
        if event is None:return None
        if event.merged_into_id is None:return event
        event_id=event.merged_into_id
    raise ValueError('Event merge cycle')
