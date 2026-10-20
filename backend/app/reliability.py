"""Public operational evidence; unknown never means healthy."""
from datetime import timedelta
from sqlalchemy import select, func, or_, false
from .models import Article, AnalysisRun, SystemState, now
from .clustering import utc
from .ai import PROMPT_VERSION
import hashlib
from .config import settings
from .catalog import directory

def reliability(db):
    current=now()
    signature=':'+hashlib.sha256((settings.ollama_model+settings.embedding_model+PROMPT_VERSION).encode()).hexdigest()[:16]
    condition=or_(Article.ai_hash.is_(None),Article.ai_hash!=Article.text_hash+signature) if settings.ai_enabled else false()
    count=db.scalar(select(func.count()).select_from(Article).where(condition))
    cooling=db.scalar(select(func.count()).select_from(Article).where(condition,Article.next_analysis_at>current))
    oldest=db.scalar(select(func.min(Article.first_seen_at)).where(condition))
    last=db.scalar(select(func.max(AnalysisRun.updated_at)).where(AnalysisRun.status=='complete',AnalysisRun.model==settings.ollama_model,AnalysisRun.prompt_version==PROMPT_VERSION))
    pipeline=db.get(SystemState,'pipeline')
    stalled=bool(count and (last is None or (current-utc(last)).total_seconds()>1800))
    sites=directory(db,limit=1000)['items']
    for s in sites:
        s['stale']=bool(s['last_success_at'] and (current-utc(s['last_success_at'])).total_seconds()>max(3600,settings.collection_interval*4))
    backup=db.get(SystemState,'backup')
    restore=db.get(SystemState,'restore_check')
    def evidence(row):
        return {'status':'stale' if (current-utc(row.updated_at)).total_seconds()>172800 else row.value.get('status'),'checked_at':row.updated_at} if row else {'status':'unverified','checked_at':None}
    alerts=[]
    if stalled:alerts.append({'code':'ai_progress_stalled','message':'AI дууссан ажил 30 минутын дотор бүртгэгдээгүй; дараалал байна.'})
    degraded=sum(s['feed_health']=='degraded' or s['stale'] for s in sites)
    if degraded:alerts.append({'code':'source_degraded','message':f'{degraded} сайтын таталт алдаатай эсвэл хоцорсон.'})
    if backup is None or evidence(backup)['status']!='completed':alerts.append({'code':'backup_unverified','message':'Production нөөцлөлт баталгаажаагүй, алдаатай эсвэл 48 цагаас хуучирсан.'})
    from .quality import summary
    if restore is None or evidence(restore)['status']!='completed':alerts.append({'code':'restore_unverified','message':'Нөөцөөс сэргээх амжилттай туршилт баталгаажаагүй эсвэл хуучирсан.'})
    return {'checked_at':current,'queue':{'pending':count,'ready':count-cooling,'retry_wait':cooling,'oldest_pending_at':oldest,'last_completed_at':last,'progress_stalled':stalled,'pipeline_updated_at':pipeline.updated_at if pipeline else None},'sources':{'total':len(sites),'with_articles':sum(s['article_count']>0 for s in sites),'healthy':sum(s['feed_health']=='ready' and not s['stale'] for s in sites),'degraded':degraded,'unverified':sum(not s['last_success_at'] for s in sites)},'backup':evidence(backup),'restore_check':evidence(restore),'alerts':alerts,'quality':summary(db)}
