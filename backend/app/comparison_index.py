"""Current archive comparison groups; connected candidates are not pairwise verdicts."""
from collections import defaultdict
from sqlalchemy import select
from .models import Article, Source, ArticleVersion, ArticleBodyCheck, SimilarityMatch
from .body_checks import VERSION, normalized, public_check
from .catalog import domain_of
from .evidence import redact
from .clustering import tokens


def comparison_groups(db,q='',domain='',kind='all',offset=0,limit=12,sort='newest'):
    rows=list(db.execute(select(Article,Source,ArticleBodyCheck,ArticleVersion.version).join(Source,Source.id==Article.source_id).outerjoin(ArticleBodyCheck,ArticleBodyCheck.article_id==Article.id).outerjoin(ArticleVersion,ArticleVersion.id==ArticleBodyCheck.article_version_id)))
    articles={a.id:(a,s,c if c and v==a.version and c.data.get('adapter')==VERSION else None) for a,s,c,v in rows}
    parent={i:i for i in articles};edges=[]
    def root(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def link(a,b,method):
        if a!=b:parent[root(a)]=root(b);edges.append((a,b,method))
    titles={};bodies={}
    for a,s,c in articles.values():
        title=normalized(a.title)
        if len(title.split())>=4:
            if title in titles:link(a.id,titles[title],'title_equal')
            else:titles[title]=a.id
        if c and c.state=='ready' and not c.data.get('truncated') and c.body_hash:
            if c.body_hash in bodies:link(a.id,bodies[c.body_hash],'body_equal')
            else:bodies[c.body_hash]=a.id
    # Recompute lexical edges against the current text instead of trusting stale matches.
    sets={}
    for m in db.scalars(select(SimilarityMatch).where(SimilarityMatch.method.in_(['sha256','token_jaccard']))):
        if m.article_id not in articles or m.other_id not in articles:continue
        a,b=articles[m.article_id][0],articles[m.other_id][0]
        for x in (a,b):
            if x.id not in sets:sets[x.id]=tokens(x)
        l,r=sets[a.id],sets[b.id];score=len(l&r)/len(l|r) if l|r else 0
        if score>=.72:link(a.id,b.id,'metadata_overlap')
    groups=defaultdict(list)
    for i in articles:groups[root(i)].append(i)
    methods=defaultdict(set)
    for a,b,m in edges:methods[root(a)].add(m)
    result=[];all_group_articles=set();all_domains=set()
    for gid,ids in groups.items():
        if len(ids)<2:continue
        members=[];families=defaultdict(list)
        for i in sorted(ids,reverse=True):
            a,s,c=articles[i];d=domain_of(a.url)
            members.append({'id':i,'title':redact(a.title),'url':a.url,'domain':d,'source':s.name,'published_at':a.published_at,'discovered_at':a.first_seen_at,'body':public_check(c)})
            if c and c.state=='ready' and not c.data.get('truncated'):families[c.body_hash].append(i)
        exact=[x for x in families.values() if len(x)>1]
        all_group_articles.update(ids);all_domains.update(x['domain'] for x in members)
        if kind=='exact' and not exact:continue
        if kind=='cross_site' and len({x['domain'] for x in members})<2:continue
        if domain and not any(x['domain']==domain for x in members):continue
        if q and not all(word in normalized(' '.join(x['title']+' '+x['domain']+' '+x['source'] for x in members)) for word in normalized(q).split()):continue
        result.append({'id':min(ids),'title':members[0]['title'],'members':members,'domains':sorted({x['domain'] for x in members}),'methods':sorted(methods[gid]),'exact_families':exact,'article_count':len(ids),'ready_count':sum(x['body']['state']=='ready' for x in members),'latest_id':max(ids)})
    result.sort(key=lambda x:(x['article_count'],x['latest_id']) if sort=='largest' else (x['latest_id'],x['article_count']),reverse=True)
    return {'items':result[offset:offset+limit],'total':len(result),'offset':offset,'limit':limit,'summary':{'groups':sum(len(x)>1 for x in groups.values()),'articles_in_groups':len(all_group_articles),'domains':len(all_domains),'archive_articles':len(articles),'checked_bodies':sum(c is not None and c.state=='ready' for a,s,c in articles.values())},'domain_options':sorted(all_domains),'scope':'Бүх архивын ижил гарчиг, одоогийн эхийн хэш, гарчиг/хураангуйн үгийн давхцлын холбоосоор бүлэглэв. Бүлэгт хамт байх нь бүх хосын бүтэн эх ижил гэсэн үг биш. Уншаагүй эх, илрээгүй холбоос үлдэж болно.'}
