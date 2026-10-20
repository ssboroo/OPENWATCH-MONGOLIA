"""Current-version, source-cited entity and semantic candidates."""
from sqlalchemy import select
from .models import Article,ArticleVersion,ArticleEmbedding,Entity,EntityMention,EvidenceItem,Claim
from .config import settings
from .ai import cosine
from .evidence import redact
from .serialization import article_data

LIMITATION='Нэр давхцах, утга ойролцоо байх нь зөвхөн нягтлах холбоосын нэр дэвшигч. Хүмүүсийн бодит харилцаа, хамтын ажиллагаа, ашиг сонирхол, буруутай үйлдлийг нотлохгүй. Ижил нэртэй өөр хүн байж болно.'

def connections(db,article):
    version=db.scalar(select(ArticleVersion).where(ArticleVersion.article_id==article.id,ArticleVersion.version==article.version))
    if version is None:return {'entities':[],'claims':[],'related':[],'limitation':LIMITATION}
    mentions=list(db.execute(select(EntityMention,Entity,EvidenceItem).join(Entity,Entity.id==EntityMention.entity_id).join(EvidenceItem,EvidenceItem.id==EntityMention.evidence_id).where(EntityMention.article_id==article.id,EvidenceItem.article_version_id==version.id).order_by(EntityMention.id).limit(30)))
    entities=[{'id':e.id,'name':redact(e.name),'kind':e.kind,'quote':redact(ev.excerpt),'evidence_id':ev.id,'version_id':version.id,'source_url':ev.source_url} for m,e,ev in mentions]
    claims=[{'kind':c.kind,'value':redact(c.value),'status':c.status,'quote':redact(ev.excerpt),'evidence_id':ev.id,'version_id':version.id,'source_url':ev.source_url} for c,ev in db.execute(select(Claim,EvidenceItem).join(EvidenceItem,Claim.evidence_id==EvidenceItem.id).where(Claim.article_id==article.id,EvidenceItem.article_version_id==version.id).order_by(Claim.id).limit(30))]
    related={}
    entity_ids={e.id for m,e,ev in mentions}
    if entity_ids:
        stmt=select(Article,Entity,EvidenceItem).join(EntityMention,EntityMention.article_id==Article.id).join(Entity,Entity.id==EntityMention.entity_id).join(EvidenceItem,EvidenceItem.id==EntityMention.evidence_id).join(ArticleVersion,ArticleVersion.id==EvidenceItem.article_version_id).where(Entity.id.in_(entity_ids),Article.id!=article.id,ArticleVersion.version==Article.version).order_by(Article.id.desc()).limit(80)
        for a,e,ev in db.execute(stmt):
            row=related.setdefault(a.id,{**article_data(a),'reasons':[]})
            reason={'method':'shared_name_candidate','name':redact(e.name),'quote':redact(ev.excerpt),'source_url':ev.source_url,'version_id':ev.article_version_id}
            if reason not in row['reasons']:row['reasons'].append(reason)
    embedding=db.get(ArticleEmbedding,article.id)
    if embedding and embedding.text_hash==article.text_hash and embedding.model==settings.embedding_model:
        stmt=select(Article,ArticleEmbedding).join(ArticleEmbedding,ArticleEmbedding.article_id==Article.id).where(Article.id!=article.id,ArticleEmbedding.model==embedding.model,ArticleEmbedding.text_hash==Article.text_hash)
        if db.bind.dialect.name=='postgresql':stmt=stmt.order_by(ArticleEmbedding.vector.cosine_distance(embedding.vector)).limit(20)
        else:stmt=stmt.order_by(Article.id.desc()).limit(2000)
        ranked=sorted([(cosine(embedding.vector,e.vector),a) for a,e in db.execute(stmt)],key=lambda pair:pair[0],reverse=True)
        for score,a in ranked[:20]:
            if score<.6:continue
            row=related.setdefault(a.id,{**article_data(a),'reasons':[]})
            row['reasons'].append({'method':'embedding_cosine','score':round(score,4),'model':embedding.model,'source_url':a.url})
    rows=list(related.values())
    rows.sort(key=lambda r:max((x.get('score',0) for x in r['reasons']),default=0),reverse=True)
    return {'entities':entities,'claims':claims,'related':rows[:20],'candidate_limit':20,'limitation':LIMITATION,'version_id':version.id,'scope':'headline_only' if not version.excerpt else 'title_and_excerpt'}
