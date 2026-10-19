"""Safe maintenance and availability observations; no inferred deletion from feed absence."""
from datetime import timedelta
import httpx
from sqlalchemy import select, delete
from .models import *
from .evidence import redact
from .security import fetch_feed
from .config import settings
from .clustering import utc, publication_lock

async def observe_article(db,article_id):
    article=db.get(Article,article_id)
    if article is None:raise ValueError('Article not found')
    try:
        await fetch_feed(article.url)
        state,status,note='reachable',200,'URL нээгдсэн; агуулгыг бүтнээр архивлаагүй.'
    except httpx.HTTPStatusError as exc:
        status=exc.response.status_code
        state='removed' if status in (404,410) else 'unknown'
        note='HTTP 404/410 ажиглагдсан.' if state=='removed' else 'HTTP хязгаарлалт; нийтлэл устсан гэж дүгнээгүй.'
    except Exception as exc:
        state,status,note='unknown',None,'Шалгалт амжилтгүй: '+type(exc).__name__
    observation=ArticleObservation(article_id=article_id,state=state,http_status=status,note=note)
    db.add(observation);db.flush();return observation

def retain_versions(db,dry_run=True):
    publication_lock(db)
    cutoff=now()-timedelta(days=max(1,settings.retention_days))
    protected=set()
    # Any reviewed snapshot is a durable audit record, including withdrawn reports.
    for report in db.scalars(select(PublicReport).where(PublicReport.state.in_(['published','withdrawn']))):
        protected.update(report.body.get('scope',{}).get('article_version_ids',[]))
    old=list(db.scalars(select(ArticleVersion).join(Article,Article.id==ArticleVersion.article_id).where(ArticleVersion.version!=Article.version,ArticleVersion.observed_at<cutoff)))
    candidates=[v for v in old if v.id not in protected]
    if not dry_run:
        for version in candidates:
            # Explicit order also supports local SQLite; DB cascades enforce production FKs.
            eids=list(db.scalars(select(EvidenceItem.id).where(EvidenceItem.article_version_id==version.id)))
            cids=list(db.scalars(select(Claim.id).where(Claim.evidence_id.in_(eids))))
            db.execute(delete(ClaimComparison).where((ClaimComparison.left_claim_id.in_(cids))|(ClaimComparison.right_claim_id.in_(cids))))
            db.execute(delete(Claim).where(Claim.id.in_(cids)))
            db.execute(delete(EntityMention).where(EntityMention.evidence_id.in_(eids)))
            db.execute(delete(EvidenceItem).where(EvidenceItem.id.in_(eids)))
            db.execute(delete(AnalysisRun).where(AnalysisRun.article_version_id==version.id))
            db.delete(version)
        db.add(AuditLog(action='maintenance.retention',detail=f'{len(candidates)} noncurrent, unpublished-evidence versions purged'))
    return {'dry_run':dry_run,'retention_days':settings.retention_days,'eligible_version_ids':[v.id for v in candidates],'protected_published_versions':len(protected),'limitation':'Одоогийн хувилбар болон нийтэлсэн/татсан тайланд ишилсэн хувилбарыг устгахгүй. Тайлангийн snapshot-д тусдаа retention/legal review шаардлагатай.'}
