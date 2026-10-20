"""Resumable catalog commissioning: explicit feeds, public headlines, news sitemaps.
Each host has a deadline; no access-control bypass or full article extraction.
"""
import asyncio
import hashlib
from datetime import timedelta
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
from sqlalchemy import select,text
from defusedxml import ElementTree
from .catalog import SITES,probe_results,domain_of
from .config import settings
from .db import Session
from .models import Source,SystemState,AuditLog,now
from .clustering import utc
from .security import fetch_feed,download
from .importers import parse_source
from .collector import ingest

PREFIX='discovery:'
ADAPTER_VERSION=3
def key(domain):return PREFIX+hashlib.sha256(domain.encode()).hexdigest()[:24]
def save_status(domain,value):
    with Session() as db:
        state=db.get(SystemState,key(domain))
        if state is None:state=SystemState(name=key(domain));db.add(state)
        state.value={'domain':domain,'adapter_version':ADAPTER_VERSION,**value};state.updated_at=now();db.commit()

def register(site,endpoint,kind,rows):
    if not rows:raise ValueError('Empty stream')
    with Session() as db:
        s=db.scalar(select(Source).where(Source.endpoint==endpoint))
        if s is None:
            s=Source(name=site['name'],publisher=site['name'],endpoint=endpoint,kind=kind,
                license='Publisher copyright retained. Public metadata distribution; no full-text republication license asserted.',
                permission_note='Operator requested indexing of public feed excerpts or public headline metadata with original publisher links. Robots policy checked; no paywall bypass.')
            db.add(s)
        if not s.active and s.permission_note and not s.permission_note.startswith('Operator requested'):
            return {'status':'review_required','format':kind,'entries':len(rows)}
        s.kind=kind;s.validated_at=now();s.checked_at=now();s.success_at=now();s.error=None;s.active=True
        if not s.license:s.license='Publisher copyright retained; public headline metadata only.'
        if not s.permission_note:s.permission_note='Operator requested indexing of public metadata and original publisher links.'
        db.flush();added=ingest(db,s,rows)
        db.add(AuditLog(action='catalog.commission',detail=site['domain']+':'+kind));db.commit()
        return {'status':'active','format':kind,'entries':len(rows),'added':added,'source_id':s.id}

def local_url(url,site):
    u=urlsplit(url)
    return u.scheme=='https' and not u.username and not u.password and u.port in (None,443) and domain_of(url)==site['domain']

async def inspect(site,probe):
    candidates=list(dict.fromkeys(([probe['feed_url']] if probe.get('feed_url') else [])+probe.get('feed_candidates',[])))
    for endpoint in candidates[:2]:
        if not local_url(endpoint,site):continue
        try:
            raw=await asyncio.wait_for(fetch_feed(endpoint),10)
            return register(site,endpoint,'rss',parse_source(raw,'rss',endpoint))
        except Exception:pass
    # fetch_feed applies the exact same DNS, HTTPS, redirect, robots and size rules to HTML.
    raw=await asyncio.wait_for(fetch_feed(site['website_url']),14)
    soup=BeautifulSoup(raw,'html.parser')
    for tag in soup.select('link[href]'):
        if any(t in tag.get('type','').lower() for t in ('rss','atom')):
            endpoint=urljoin(site['website_url'],tag['href'])
            if local_url(endpoint,site) and endpoint not in candidates and '/comments/' not in endpoint:
                try:
                    feed=await asyncio.wait_for(fetch_feed(endpoint),7)
                    return register(site,endpoint,'rss',parse_source(feed,'rss',endpoint))
                except Exception:pass
                break
    try:return register(site,site['website_url'],'html',parse_source(raw,'html',site['website_url']))
    except ValueError:pass
    # Only publisher-declared sitemap URLs; no guessed endpoints or recursive crawling.
    robots=await asyncio.wait_for(download(urljoin(site['website_url'],'/robots.txt')),5)
    maps=[line.split(':',1)[1].strip() for line in robots.decode('utf-8','replace').splitlines() if line.lower().startswith('sitemap:')]
    for endpoint in maps[:2]:
        if not local_url(endpoint,site):continue
        xml=await asyncio.wait_for(fetch_feed(endpoint),7)
        root=ElementTree.fromstring(xml)
        if root.tag.rsplit('}',1)[-1]=='sitemapindex':
            children=[c.text for c in root.iter() if c.tag.rsplit('}',1)[-1]=='loc' and c.text]
            endpoint=next((u for u in children if 'news' in u.lower() and local_url(u,site)),None)
            if not endpoint:continue
            xml=await asyncio.wait_for(fetch_feed(endpoint),7)
        rows=parse_source(xml,'sitemap',endpoint)
        rows=[r for r in rows if r['source_metadata'].get('sitemap_has_title')]
        if rows:return register(site,endpoint,'sitemap',rows)
    return {'status':'no_public_stream','reason':'No public feed, readable headline list or news sitemap found'}

async def commission():
    # One catalog scan across all worker replicas. A dedicated connection owns the lock.
    with Session() as lockdb:
        if lockdb.bind.dialect.name=='postgresql' and not lockdb.scalar(text('SELECT pg_try_advisory_lock(20471023)')):return
        try:
            probes=probe_results();cutoff=now()-timedelta(hours=24)
            with Session() as db:
                done={s.value.get('domain') for s in db.scalars(select(SystemState).where(SystemState.name.like(PREFIX+'%'))) if utc(s.updated_at)>cutoff and (s.value.get('status')=='active' or s.value.get('adapter_version',1)>=ADAPTER_VERSION)}
            sem=asyncio.Semaphore(max(1,min(settings.catalog_concurrency,12)))
            processed=len(done)
            def progress(status):
                with Session() as db:
                    from .pipeline import heartbeat
                    heartbeat(db,'catalog_discovery',{'status':status,'processed':processed,'total':len(SITES)});db.commit()
            async def one(site):
                nonlocal processed
                if site['domain'] in done:return
                async with sem:
                    try:result=await asyncio.wait_for(inspect(site,probes.get(site['domain'],{})),max(10,settings.catalog_site_timeout))
                    except asyncio.TimeoutError:result={'status':'timeout','reason':'Host deadline exceeded; web search remains available'}
                    except Exception as exc:result={'status':'unavailable','reason':type(exc).__name__}
                    save_status(site['domain'],result);processed+=1;progress('running')
            progress('running')
            ordered=sorted(SITES,key=lambda site:site['domain'] not in {'sonin.mn','lemonpress.mn','ublife.mn'})
            await asyncio.gather(*(one(site) for site in ordered))
            progress('completed')
        finally:
            if lockdb.bind.dialect.name=='postgresql':lockdb.execute(text('SELECT pg_advisory_unlock(20471023)'))


async def supervisor():
    while True:
        try:
            await commission()
            await asyncio.sleep(86400)
        except Exception as exc:
            import json
            print(json.dumps({'service':'catalog_discovery','status':'retrying','error':type(exc).__name__}),flush=True)
            await asyncio.sleep(60)
