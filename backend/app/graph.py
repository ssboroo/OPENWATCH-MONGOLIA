from sqlalchemy import select
from .models import ArticleVersion, Article, Source, EventArticle, EvidenceItem, EntityMention, Entity
from .clustering import canonical_event
from .evidence import redact
from .catalog import domain_of

def evidence_graph(db,event_id,freshness='all'):
    from .search_filters import fresh
    event=canonical_event(db,event_id)
    if event is None:raise ValueError('Event not found')
    articles=list(db.scalars(fresh(select(Article).join(EventArticle,EventArticle.article_id==Article.id).where(EventArticle.event_id==event.id).order_by(Article.id).limit(100),db,freshness)))
    ids=[a.id for a in articles];nodes=[{'id':f'event:{event.id}','type':'event','label':redact(event.title)}];links=[];seen={n['id'] for n in nodes}
    for a in articles:
        s=db.get(Source,a.source_id);sid=f'source:{s.id}';aid=f'article:{a.id}'
        if sid not in seen:nodes.append({'id':sid,'type':'publisher','label':s.name});seen.add(sid)
        nodes.append({'id':aid,'type':'article','label':redact(a.title),'url':a.url})
        links.extend([{'source':sid,'target':aid,'relation':'published' if domain_of(a.url)==domain_of(s.endpoint) else 'feed_references','evidence_url':a.url,'method':'feed_metadata','confidence':1.0,'detected_at':a.first_seen_at},{'source':aid,'target':f'event:{event.id}','relation':'reported_same_event_candidate','evidence_url':a.url,'method':'content_similarity','confidence':None,'detected_at':a.first_seen_at}])
    query=select(EntityMention,Entity,EvidenceItem).join(Entity,EntityMention.entity_id==Entity.id).join(EvidenceItem,EntityMention.evidence_id==EvidenceItem.id).join(ArticleVersion,ArticleVersion.id==EvidenceItem.article_version_id).join(Article,Article.id==EntityMention.article_id).where(EntityMention.article_id.in_(ids),ArticleVersion.version==Article.version).order_by(EntityMention.id).limit(300)
    for mention,entity,ev in db.execute(query):
        nid=f'entity:{entity.id}'
        if nid not in seen:nodes.append({'id':nid,'type':entity.kind,'label':redact(entity.name)});seen.add(nid)
        links.append({'source':f'article:{mention.article_id}','target':nid,'relation':'mentions','evidence_id':ev.id,'evidence_url':ev.source_url,'quote':redact(ev.excerpt),'method':mention.method,'confidence':mention.confidence,'detected_at':mention.created_at or ev.observed_at})
    return {'event_id':event.id,'nodes':nodes,'links':links,'truncated':len(articles)==100 or len(links)>=500,'limitation':'Холбоос нь нийтэлсэн, нэг үйл явдалд хамаарах нэр дэвшигч эсвэл нэр дурдсан гэдгийг л илэрхийлнэ. Хамтын ажиллагаа, ашиг сонирхол, буруутай үйлдэл, улс төрийн үзэл бодлыг нотлохгүй.'}
