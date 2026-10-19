"""Read-only, version-grounded research; no generated claims or truth scores."""
from sqlalchemy import select, func, or_
from .models import Article, ArticleVersion, Source, now
from .evidence import PATTERNS, privacy_flags, redact
from .search_filters import scope

LIMITATION = 'Архивт хадгалсан гарчиг, хураангуйн хайлт. Эшлэл нь нийтлэгчийн мэдэгдэл болохоос үнэн зөвийн баталгаа биш. Өөр сайт дээр давтагдсан нь бие даасан баталгаа биш. Тоон ялгааг автоматаар зөрчил гэж дүгнээгүй. Бүтэн эх болон анхны баримтыг эх холбоосоор нягтална.'

def research(db, q, domain='', category='', date_from=None, date_to=None, date_field='discovered', offset=0, limit=20):
    from fastapi import HTTPException
    terms=list(dict.fromkeys(q.split()))
    if not terms or len(terms)>12:raise HTTPException(422,'Use 1–12 search terms')
    stmt=select(Article,ArticleVersion,Source).join(ArticleVersion,(ArticleVersion.article_id==Article.id)&(ArticleVersion.version==Article.version)).join(Source,Source.id==Article.source_id)
    for term in terms:
        escaped=term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        stmt=stmt.where(or_(ArticleVersion.title.ilike('%'+escaped+'%',escape='\\'),ArticleVersion.excerpt.ilike('%'+escaped+'%',escape='\\')))
    stmt=scope(stmt,db,domain=domain,category=category,date_from=date_from,date_to=date_to,date_field=date_field)
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    items=[]
    for a,v,s in db.execute(stmt.order_by(Article.first_seen_at.desc(),Article.id.desc()).offset(offset).limit(limit)):
        quotes=[];claims=[]
        for field,text in [('title',v.title),('excerpt',v.excerpt)]:
            if not text:continue
            quotes.append({'field':field,'text':redact(text),'redacted':redact(text)!=text,'start_offset':0 if field=='title' else len(v.title)+1,'end_offset':len(text) if field=='title' else len(v.title)+1+len(text)})
            for kind,pattern in PATTERNS:
                for match in pattern.finditer(text):
                    if not privacy_flags(match.group()):claims.append({'kind':kind,'value':redact(match.group()),'field':field,'status':'unverified'})
        items.append({'article_id':a.id,'title':redact(v.title),'source':s.name,'source_url':a.url,'published_at':a.published_at,'discovered_at':a.first_seen_at,'observed_at':v.observed_at,'version':v.version,'version_id':v.id,'text_hash':v.text_hash,'scope':'headline_only' if not v.excerpt else 'title_and_excerpt','quotes':quotes,'claims':claims[:30]})
    return {'query':q,'mode':'all_terms','generated_at':now(),'total':total,'offset':offset,'limit':limit,'items':items,'limitation':LIMITATION}
