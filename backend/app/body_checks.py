"""Robots-respecting transient body reads; retain hashes and at most 600 lead characters."""
import asyncio,hashlib,json,re,unicodedata
from datetime import timedelta
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from sqlalchemy import select,func,or_,and_,text
from sqlalchemy.exc import IntegrityError
from .models import Article,ArticleVersion,ArticleBodyCheck,Source,now
from .db import Session
from .security import fetch_feed
from .evidence import redact
from .catalog import domain_of
from .clustering import utc

VERSION='body-fingerprint-v2'
LIMIT=80000
K=256
LABELS={'сурталчилгаа','төлбөртэй мэдээ','төлбөртэй нийтлэл','хамтран бэлтгэв','sponsored','advertorial','paid content','paid partnership'}
JOBS=set()
SELECTORS=['[itemprop="articleBody"]','#mvp-content-main','.entry-content','.post-content','.article-content','.article-body','.news-body','.news_content','.news-content','.news_text','.post_text','.content-text','#news-body','article']

def normalized(s):return ' '.join(unicodedata.normalize('NFKC',s).casefold().split())
def words(s):return re.findall(r'\w+',normalized(s))
def hash_text(s):return hashlib.sha256(s.encode()).hexdigest()

def extract_body(raw,expected_title=''):
    soup=BeautifulSoup(raw,'html.parser')
    bodies=[]
    for tag in soup.select('script[type="application/ld+json"]')[:20]:
        try:
            root=json.loads(tag.string or tag.get_text());stack=root if isinstance(root,list) else [root]
            examined=0
            while stack and examined<30:
                row=stack.pop(0);examined+=1
                if not isinstance(row,dict):continue
                if isinstance(row.get('@graph'),list):stack.extend(row['@graph'][:30])
                if row.get('isAccessibleForFree') is False:return None
                kinds=row.get('@type',[]);kinds=[kinds] if isinstance(kinds,str) else kinds
                if isinstance(kinds,list) and any(k in ('NewsArticle','Article','ReportageNewsArticle') for k in kinds) and isinstance(row.get('articleBody'),str):bodies.append(BeautifulSoup(row['articleBody'],'html.parser').get_text(' ',strip=True))
        except (ValueError,TypeError):pass
    disclosures=[]
    for tag in soup.select('meta[name="genre"],meta[property="article:section"],.article-label,.post-label,.entry-category,.article-category,.news-category')[:50]:
        label=' '.join((tag.get('content') or tag.get_text(' ',strip=True)).split())
        if normalized(label) in LABELS:disclosures.append({'quote':redact(label[:160]),'method':'publisher_label'})
    for tag in soup.select('script,style,nav,header,footer,aside,form,noscript,.related,.related-news,.share,.social,.advertisement,.ads'):tag.decompose()
    json_bodies=[x for x in bodies if len(x)>=250 and len(words(x))>=40]
    bodies=json_bodies[:1]
    for selector in ([] if bodies else SELECTORS):
        for tag in soup.select(selector)[:4]:
            for headline in tag.select('h1'):headline.decompose()
            value=tag.get_text(' ',strip=True)
            if len(value)>=250 and len(words(value))>=40:bodies.append(value)
        if bodies:break
    if not bodies and expected_title:
        for heading in soup.select('h1')[:3]:
            if SequenceMatcher(None,words(heading.get_text(' ',strip=True)),words(expected_title),autojunk=False).ratio()<.55:continue
            parent=heading.parent
            for _ in range(4):
                if parent is None or parent.name in ('body','html'):break
                value=' '.join(p.get_text(' ',strip=True) for p in parent.select('p'))
                if len(value)>=250 and len(words(value))>=40:
                    bodies.append(value);break
                parent=parent.parent
            if bodies:break
    bodies=[x.strip() for x in bodies if len(x.strip())>=250 and len(words(x))>=40]
    if not bodies:return None
    body=max(bodies,key=len)
    prefix=normalized(body[:180])
    for label in LABELS:
        if label not in {'сурталчилгаа','хамтран бэлтгэв'} and (prefix.startswith(label+':') or prefix.startswith(label+' /')):
            disclosures.append({'quote':redact(body[:min(160,len(label)+60)]),'method':'explicit_body_prefix'})
    truncated=len(body)>LIMIT;body=body[:LIMIT]
    promotion=[]
    for phrase in ('худалдан аваарай','захиалаарай','онцгой хямдрал','утсаар захиалах','buy now','order now'):
        at=body.casefold().find(phrase)
        if at>=0:promotion.append({'phrase':phrase,'quote':redact(body[max(0,at-35):at+105]),'method':'commercial_phrase_observed'})
    credits=[]
    for m in re.finditer(r'(?:Эх\s*сурвалж|Source)\s*[:：]\s*.{5,120}',body,re.I):credits.append(redact(m.group()))
    tokens=words(body)
    shingles={hash_text(' '.join(tokens[i:i+5]))[:16] for i in range(max(0,len(tokens)-4))}
    return {'adapter':VERSION,'body_hash':hash_text(normalized(body)),'characters':len(body),'word_count':len(tokens),'shingle_count':len(shingles),'signature':sorted(shingles)[:K],'lead':redact(body[:600]),'truncated':truncated,'disclosures':disclosures[:3],'promotion_signals':promotion[:3],'source_credits':credits[:2],'scope':'truncated_body' if truncated else 'extracted_article_body','retention':'Full body was read transiently; only derived fingerprints and a short lead are retained.'}

def current_check(db,a):
    c=db.get(ArticleBodyCheck,a.id)
    if c:
        v=db.get(ArticleVersion,c.article_version_id)
        if v and v.version==a.version and c.data.get('adapter')==VERSION:return c
    return None

async def check_article(article_id,fetcher=fetch_feed,force=False):
    with Session() as db:
        a=db.get(Article,article_id)
        if a is None:return {'state':'not_found'}
        old=current_check(db,a)
        if old and not force and (now()-utc(old.checked_at)).total_seconds()<21600:return {'state':old.state,'cached':True}
        v=db.scalar(select(ArticleVersion).where(ArticleVersion.article_id==a.id,ArticleVersion.version==a.version))
        if v is None:return {'state':'no_version'}
        url=a.url;vid=v.id;expected=a.text_hash;source=db.get(Source,a.source_id);active=bool(source and source.active)
    try:
        if not active:state='source_inactive';data={'reason':'Collection is disabled for this source.'}
        else:
            raw=await asyncio.wait_for(fetcher(url),timeout=25)
            data=extract_body(raw,a.title)
            state='ready' if data else 'no_body'
            data=data or {'reason':'No reliable article-body container or articleBody metadata found.'}
    except asyncio.TimeoutError:state='timeout';data={'reason':'Publisher body read exceeded deadline.'}
    except Exception as exc:
        state='blocked' if 'robots' in str(exc).casefold() else 'unavailable'
        data={'reason':'Publisher body could not be read under network/robots policy.','error_type':type(exc).__name__}
    with Session() as db:
        a=db.get(Article,article_id)
        if a is None or a.text_hash!=expected or a.version!=v.version:return {'state':'superseded'}
        row=db.get(ArticleBodyCheck,article_id)
        if row is None:row=ArticleBodyCheck(article_id=article_id);db.add(row)
        row.article_version_id=vid;row.state=state;row.data={**data,'adapter':VERSION};row.body_hash=data.get('body_hash');row.checked_at=now()
        try:db.commit()
        except IntegrityError:
            db.rollback()
            existing=db.get(ArticleBodyCheck,article_id)
            if existing is None or existing.article_version_id!=vid:raise
            state=existing.state
    return {'state':state,'article_id':article_id}

def body_overlap(a,b):
    if not a or not b:return None
    if a.get('body_hash') and a.get('body_hash')==b.get('body_hash'):return 1.0
    left=set(a.get('signature',[]));right=set(b.get('signature',[]))
    sample=sorted(left|right)[:K]
    if not sample:return None
    return sum(x in left and x in right for x in sample)/len(sample)

def public_check(c):
    if c is None:return {'state':'not_checked','disclosure':'unknown'}
    d=c.data
    return {'state':c.state,'checked_at':c.checked_at,'body_hash':c.body_hash,'scope':d.get('scope'),'word_count':d.get('word_count'),'characters':d.get('characters'),'truncated':d.get('truncated',False),'lead':d.get('lead',''),'disclosure':'explicit_label_found' if d.get('disclosures') else 'not_observed' if c.state=='ready' else 'unknown','disclosures':d.get('disclosures',[]),'promotion_signals':d.get('promotion_signals',[]),'source_credits':d.get('source_credits',[]),'reason':d.get('reason'),'version_id':c.article_version_id}

def compare_archive(db,a,other_id=None):
    own=current_check(db,a);own_data=own.data if own and own.state=='ready' else None
    title=words(a.title)
    query=select(Article,Source,ArticleBodyCheck,ArticleVersion.version).join(Source,Article.source_id==Source.id).outerjoin(ArticleBodyCheck,ArticleBodyCheck.article_id==Article.id).outerjoin(ArticleVersion,ArticleVersion.id==ArticleBodyCheck.article_version_id).where(Article.id!=a.id)
    if other_id is not None:query=query.where(Article.id==other_id)
    rows=list(db.execute(query.order_by(Article.id.desc()).limit(5000)))
    if other_id is None and own and own.body_hash:
        extra=db.execute(select(Article,Source,ArticleBodyCheck,ArticleVersion.version).join(Source,Article.source_id==Source.id).join(ArticleBodyCheck,ArticleBodyCheck.article_id==Article.id).join(ArticleVersion,ArticleVersion.id==ArticleBodyCheck.article_version_id).where(Article.id!=a.id,ArticleBodyCheck.body_hash==own.body_hash).limit(50))
        seen={x[0].id for x in rows};rows.extend(x for x in extra if x[0].id not in seen)
    result=[];ready=0
    for other,source,c,body_version in rows:
        # Old body snapshots never compare against a changed metadata version.
        if c and (body_version!=other.version or c.data.get('adapter')!=VERSION):c=None
        data=c.data if c and c.state=='ready' else None
        ready+=int(data is not None)
        score=SequenceMatcher(None,title,words(other.title),autojunk=False).ratio()
        overlap=body_overlap(own_data,data)
        left_coverage=right_coverage=None
        if overlap is not None and own_data and data:
            n=own_data.get('shingle_count',0);m=data.get('shingle_count',0)
            intersection=overlap*(n+m)/(1+overlap)
            left_coverage=min(1.,intersection/n) if n else 0.
            right_coverage=min(1.,intersection/m) if m else 0.
        same=bool(own_data and data and own_data['body_hash']==data['body_hash'])
        potential_containment=left_coverage is not None and max(left_coverage,right_coverage)>=.75
        if other_id is None and not same and not (overlap is not None and overlap>=.45) and not potential_containment and not (len(title)>=4 and score>=.70):continue
        excerpts=[]
        if own_data and data:
            left=own_data.get('lead','');right=data.get('lead','');match=SequenceMatcher(None,left,right,autojunk=False).find_longest_match()
            if match.size>=40:excerpts=[{'quote':left[match.a:match.a+min(match.size,160)],'left_url':a.url,'right_url':other.url,'method':'exact_shared_lead_passage'}]
        contained=bool(left_coverage is not None and max(left_coverage,right_coverage)>=.75 and excerpts and len(excerpts[0]['quote'])>=80)
        if other_id is None and not same and not contained and not (overlap is not None and overlap>=.45) and not (len(title)>=4 and score>=.70):continue
        kind='observed_body_equal' if same and (own_data.get('truncated') or data.get('truncated')) else 'normalized_body_equal' if same else 'body_overlap_candidate' if overlap is not None and overlap>=.45 else 'body_containment_candidate' if contained else 'title_only_candidate' if len(title)>=4 and score>=.70 else 'no_strong_match' if overlap is not None else 'insufficient_body'
        result.append({'id':other.id,'title':redact(other.title),'url':other.url,'source':source.name,'domain':domain_of(other.url),'version':other.version,'published_at':other.published_at,'discovered_at':other.first_seen_at,'title_similarity':round(score,4),'body_similarity':round(overlap,4) if overlap is not None else None,'comparison':kind,'left_body_coverage':round(left_coverage,4) if left_coverage is not None else None,'right_body_coverage':round(right_coverage,4) if right_coverage is not None else None,'same_site':domain_of(a.url)==domain_of(other.url),'shared_passages':excerpts,'body':public_check(c)})
    result.sort(key=lambda r:(r['comparison']=='normalized_body_equal',r['body_similarity'] or 0,r['title_similarity']),reverse=True)
    exact=[x for x in result if x['comparison']=='normalized_body_equal']
    family={'matching_articles':len(exact)+int(own_data is not None),'domains':sorted({domain_of(a.url)}|{x['domain'] for x in exact}) if own_data else []}
    return {'content_family':family,'article_id':a.id,'title':redact(a.title),'url':a.url,'published_at':a.published_at,'discovered_at':a.first_seen_at,'body':public_check(own),'items':result[:20],'candidate_count':len(rows),'body_candidates_checked':ready,'candidate_limit':5000,'limitation':'Энэ нь эхийн ижил/төстэй байдлын шалгалт. Ижил эх нь хуулбар, хамтын хэвлэлийн мэдээ эсвэл зөвшөөрөлтэй дахин нийтлэл байж болно; хэн хэнээс хуулсныг тогтоохгүй. Төлбөртэй тэмдэглэгээ олдоогүй нь захиалгат бишийн баталгаа биш. Бүтэн эх уншигдаагүй тохиолдолд гарчгаар бүтэн агуулгыг дүгнэхгүй. 5 үгийн хэсгийн bottom-k Jaccard нь ойролцоо хэмжилт, ижил эхийн SHA-256 нь нормчилсон татсан эхэд хамаарна.'}

async def body_batch():
    with Session() as lock:
        pg=lock.bind.dialect.name=='postgresql'
        if pg and not lock.scalar(text('SELECT pg_try_advisory_lock(20471025)')):return {'status':'already_running'}
        try:
            with Session() as db:
                q=select(Article.id).join(Source,Source.id==Article.source_id).join(ArticleVersion,and_(ArticleVersion.article_id==Article.id,ArticleVersion.version==Article.version)).outerjoin(ArticleBodyCheck,ArticleBodyCheck.article_id==Article.id).where(Source.active.is_(True),or_(ArticleBodyCheck.article_id.is_(None),ArticleBodyCheck.article_version_id!=ArticleVersion.id,ArticleBodyCheck.checked_at<now()-timedelta(hours=24),ArticleBodyCheck.data['adapter'].as_string().is_(None),ArticleBodyCheck.data['adapter'].as_string()!=VERSION))
                ids=list(db.scalars(q.order_by(Article.id.desc()).limit(3)))
                ids+=list(db.scalars(q.where(Article.id.not_in(ids)).order_by(Article.id).limit(3)))
            sem=asyncio.Semaphore(3)
            async def one(id):
                async with sem:return await check_article(id)
            results=await asyncio.gather(*(one(id) for id in ids))
            return {'status':'completed','processed':len(results),'ready':sum(x['state']=='ready' for x in results)}
        finally:
            if pg:lock.execute(text('SELECT pg_advisory_unlock(20471025)'))


async def check_with_neighbors(article_id,fetcher=fetch_feed):
    try:
        await check_article(article_id,fetcher,force=True)
        with Session() as db:
            a=db.get(Article,article_id)
            if a is None:return
            neighbors=[r['id'] for r in compare_archive(db,a)['items'] if r['body']['state']=='not_checked'][:2]
        for id in neighbors:await check_article(id,fetcher)
    finally:JOBS.discard(article_id)

def coverage(db):
    total=db.scalar(select(func.count()).select_from(Article))
    valid=select(ArticleBodyCheck.state).join(Article,Article.id==ArticleBodyCheck.article_id).join(ArticleVersion,ArticleVersion.id==ArticleBodyCheck.article_version_id).where(ArticleVersion.version==Article.version,ArticleBodyCheck.data['adapter'].as_string()==VERSION).subquery()
    counts=dict(db.execute(select(valid.c.state,func.count()).group_by(valid.c.state)).all())
    return {'articles':total,'checked':sum(counts.values()),'ready':counts.get('ready',0),'states':counts}
