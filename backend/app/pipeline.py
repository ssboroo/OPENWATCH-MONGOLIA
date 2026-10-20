"""Durable database state, bounded batches, local AI optional, grounded fallback."""
import asyncio
import hashlib
from datetime import timedelta
from sqlalchemy import select, or_, and_, text, delete
from .models import Article, ArticleVersion, ArticleEmbedding, AnalysisRun, SimilarityMatch, SystemState, now
from .db import Session
from .config import settings
from .ai import Ollama, InferenceFailure, PROMPT_VERSION, LIMITATION, cosine, language_hint
from .evidence import full_text, lexical_claims, evidence_for, add_entity, add_claim
from .clustering import rebuild_events


def model_hash(article):
    return article.text_hash+':'+hashlib.sha256((settings.ollama_model+settings.embedding_model+PROMPT_VERSION).encode()).hexdigest()[:16]

def heartbeat(db,name,value):
    row=db.get(SystemState,name)
    if row is None:row=SystemState(name=name);db.add(row)
    row.value=value;row.updated_at=now();db.flush()

def add_semantic_matches(db,article,embedding):
    db.execute(delete(SimilarityMatch).where(or_(SimilarityMatch.article_id==article.id,SimilarityMatch.other_id==article.id),SimilarityMatch.method=='embedding_cosine'))
    stmt=select(ArticleEmbedding).join(Article,Article.id==ArticleEmbedding.article_id).where(ArticleEmbedding.article_id!=article.id,ArticleEmbedding.model==embedding.model,ArticleEmbedding.text_hash==Article.text_hash)
    if db.bind.dialect.name=='postgresql':
        stmt=stmt.order_by(ArticleEmbedding.vector.cosine_distance(embedding.vector)).limit(50)
    else:stmt=stmt.order_by(ArticleEmbedding.article_id.desc()).limit(1000)
    for other in db.scalars(stmt):
        score=cosine(embedding.vector,other.vector)
        if score<settings.semantic_threshold:continue
        a,b=sorted([article.id,other.article_id])
        existing=db.scalar(select(SimilarityMatch).where(SimilarityMatch.article_id==a,SimilarityMatch.other_id==b))
        if existing is None:db.add(SimilarityMatch(article_id=a,other_id=b,method='embedding_cosine',score=score))
    db.flush()

async def analyze_article(article_id,ollama=None):
    client=ollama or Ollama()
    with Session() as db:
        article=db.get(Article,article_id)
        if article is None:return {'status':'not_found'}
        version=db.scalar(select(ArticleVersion).where(ArticleVersion.article_id==article_id,ArticleVersion.version==article.version))
        if version is None:return {'status':'no_version'}
        text_source=full_text(version);expected_hash=article.text_hash;vid=version.id;metadata_only=article.source_metadata.get('metadata_only',False)
    extraction=vector=None;error=None
    if settings.ai_enabled:
        try:
            extraction=await client.extract(text_source)
        except InferenceFailure as exc:error=str(exc)
        # Embedding can remain useful even when strict extraction rejects a response.
        try:
            vector=await client.embed(text_source)
        except InferenceFailure as exc:error=(error+'; ' if error else '')+str(exc)
    with Session() as db:
        article=db.scalar(select(Article).where(Article.id==article_id).with_for_update())
        if article is None or article.text_hash!=expected_hash:return {'status':'superseded'}
        version=db.get(ArticleVersion,vid)
        lexical_claims(db,article,version)
        model=settings.ollama_model if settings.ai_enabled else 'deterministic'
        run=db.scalar(select(AnalysisRun).where(AnalysisRun.article_version_id==vid,AnalysisRun.model==model,AnalysisRun.prompt_version==PROMPT_VERSION))
        if run is None:
            run=AnalysisRun(article_id=article_id,article_version_id=vid,model=model,prompt_version=PROMPT_VERSION,limitation=LIMITATION)
            db.add(run)
        else:run.attempts+=1
        if not settings.ai_enabled:run.limitation='Локал AI унтраалттай. Зөвхөн эхийн гарчиг, дүрмийн шинжилгээ ашигласан; баримтыг баталгаажуулаагүй.'
        run.evidence_urls=[article.url];run.error=error;run.updated_at=now()
        run.status='complete' if extraction is not None and error is None else 'fallback'
        # No generated fallback prose: extractive title/excerpt with source attribution.
        quotes=extraction.summary_quotes if extraction is not None else [version.title]
        for quote in quotes:evidence_for(db,article,version,quote,'model_extractive_v1' if extraction else 'source_title_v1')
        run.limitation=LIMITATION if settings.ai_enabled else run.limitation
        if metadata_only:run.limitation+=' Зөвхөн гарчгийн хүрээнд шинжилсэн; бүтэн эхийг уншаагүй.'
        run.result={'scope':'headline_only' if metadata_only else 'title_and_excerpt','summary_quotes':quotes,'language_hint':language_hint(text_source),'category':extraction.category if extraction else 'other','source_article_ids':[article_id],'embedding_model':settings.embedding_model if vector is not None else None}
        run.confidence=extraction.confidence if extraction is not None else 0.0
        if extraction is not None:
            for entity in extraction.entities:
                add_entity(db,article,version,entity.kind,entity.name,entity.quote,extraction.confidence)
            for claim in extraction.claims:
                add_claim(db,article,version,claim.kind,claim.value,claim.quote,method='model_extractive_v1')
        if vector is not None:
            embedding=db.get(ArticleEmbedding,article_id)
            if embedding is None:embedding=ArticleEmbedding(article_id=article_id);db.add(embedding)
            embedding.text_hash=expected_hash;embedding.model=settings.embedding_model;embedding.vector=vector;embedding.dimensions=1024;embedding.created_at=now();db.flush()
            add_semantic_matches(db,article,embedding)
            article.ai_hash=model_hash(article) if extraction is not None and error is None else None
        article.analysis_hash=expected_hash
        article.analysis_status='ai_complete' if run.status=='complete' else 'ai_unavailable' if error else 'metadata_only' if metadata_only else 'lexical_only'
        article.next_analysis_at=now()+timedelta(seconds=max(60,settings.ai_retry_seconds)) if error else None
        heartbeat(db,'ai',{'status':article.analysis_status,'article_id':article_id,'enabled':settings.ai_enabled,'error':error})
        db.commit()
        return {'status':article.analysis_status,'article_id':article_id}

async def process_batch(ollama=None):
    with Session() as lockdb:
        pg=lockdb.bind.dialect.name=='postgresql'
        if pg and not lockdb.scalar(text('SELECT pg_try_advisory_lock(20471020)')):return {'status':'already_running'}
        try:
            with Session() as db:
                condition=or_(Article.analysis_hash.is_(None),Article.analysis_hash!=Article.text_hash)
                if settings.ai_enabled:
                    signature=':'+hashlib.sha256((settings.ollama_model+settings.embedding_model+PROMPT_VERSION).encode()).hexdigest()[:16]
                    condition=or_(condition,and_(or_(Article.ai_hash.is_(None),Article.ai_hash!=Article.text_hash+signature),or_(Article.next_analysis_at.is_(None),Article.next_analysis_at<=now())))
                batch=max(1,min(settings.ai_batch_size,4 if settings.ai_enabled else 100))
                candidates=select(Article.id).where(condition,or_(Article.next_analysis_at.is_(None),Article.next_analysis_at<=now()))
                # Split capacity between fresh news and archive backfill; neither starves.
                ids=list(db.scalars(candidates.order_by(Article.id.desc()).limit((batch+1)//2)))
                ids+=list(db.scalars(candidates.where(Article.id.not_in(ids)).order_by(Article.id).limit(batch-len(ids))))
                heartbeat(db,'pipeline',{'status':'running','batch_size':len(ids)});db.commit()
            results=[]
            for article_id in ids:
                try:results.append(await analyze_article(article_id,ollama))
                except Exception as exc:
                    results.append({'article_id':article_id,'status':'error','error':type(exc).__name__})
                    with Session() as db:
                        article=db.get(Article,article_id)
                        if article:
                            article.analysis_status='error';article.next_analysis_at=now()+timedelta(seconds=max(60,settings.ai_retry_seconds));db.commit()
            with Session() as db:
                rebuild_events(db)
                from .reports import build_changed_reports
                report_ids=build_changed_reports(db,ids)
                heartbeat(db,'pipeline',{'status':'completed','processed':len(ids),'reports':len(report_ids),'results':results});db.commit()
            return {'status':'completed','items':results,'draft_report_ids':report_ids}
        finally:
            if pg:lockdb.execute(text('SELECT pg_advisory_unlock(20471020)'))
