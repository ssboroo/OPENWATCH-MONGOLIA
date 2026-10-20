"""Versioned media directory and honest links to external web search.

Directory order is editorial and is not a traffic or credibility ranking.
A reachable homepage never implies valid feed, permission or collector activation.
"""
import json
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from sqlalchemy import select, func
from .models import Source, Article, SystemState

DATA = Path(__file__).parent / 'data'
SITES = json.loads((DATA / 'mongolia-sites.v2.json').read_text())
BY_DOMAIN = {site['domain']: site for site in SITES}

def probe_results():
    merged={}
    for name in ('probe-all-2026-10-19.json','probe-2026-10-19.json','probe-expanded-2026-10-20.json'):
        path=DATA/name
        if path.exists():
            for row in json.loads(path.read_text()):
                if row['domain'] in BY_DOMAIN:merged[row['domain']]={**merged.get(row['domain'],{}),**row}
    return merged

def domain_of(url):
    host = (urlsplit(url).hostname or '').lower()
    return host.removeprefix('www.')

def web_search_link(query, domains, engine='google', date_from=None, date_to=None):
    if not query.strip():
        raise ValueError('Search query is required')
    if not domains or len(domains)>100 or any(d not in BY_DOMAIN for d in domains):
        raise ValueError('Choose registered media domains')
    # Quote sites structurally, not user input; query syntax remains user-controlled
    # only in the external search engine, never as a local fetch URL.
    restriction=' OR '.join('site:'+d for d in domains)
    q='('+restriction+') '+query.strip()
    base='https://www.google.com/search' if engine=='google' else 'https://www.bing.com/search'
    params={'q':q}
    if date_from or date_to:
        if engine!='google':raise ValueError('Date range links currently support Google only')
        start=date_from.strftime('%m/%d/%Y') if date_from else ''
        end=date_to.strftime('%m/%d/%Y') if date_to else ''
        params['tbs']=f'cdr:1,cd_min:{start},cd_max:{end}'
    return base+'?'+urlencode(params)

def directory(db, query='', category='', availability='', offset=0, limit=20):
    probes=probe_results()
    discoveries={s.value.get('domain'):{**s.value,'checked_at':s.updated_at.isoformat()} for s in db.scalars(select(SystemState).where(SystemState.name.like('discovery:%')))}
    sources=list(db.scalars(select(Source)))
    counts=dict(db.execute(select(Article.source_id,func.count(Article.id)).group_by(Article.source_id)).all())
    groups={}
    for source in sources:
        groups.setdefault(domain_of(source.endpoint),[]).append(source)
    rows=[]
    for site in SITES:
        if query and query.casefold() not in (site['name']+' '+site['domain']).casefold():
            continue
        if category and category != site['category']:
            continue
        probe=probes.get(site['domain'],{})
        linked=groups.get(site['domain'],[])
        active=[s.id for s in linked if s.active]
        if availability=='active' and not active:continue
        if availability=='reachable' and probe.get('homepage_status')!='reachable':continue
        if availability=='feed_found' and not (probe.get('feed_url') or any(s.validated_at for s in linked)):continue
        success=[s for s in linked if s.active and s.success_at]
        last_success=max((s.success_at for s in success),default=None)
        health='degraded' if any(s.active and s.error for s in linked) else 'ready' if success else 'validated' if any(s.active and s.validated_at for s in linked) else 'not_active'
        rows.append({**site,'probe':probe,'source_ids':[s.id for s in linked], 'active_source_ids':active, 'archive_status':'active' if active else 'not_active','discovery':discoveries.get(site['domain'],{}),'feed_health':health,'last_success_at':last_success,'last_checked_at':max((s.checked_at for s in linked if s.checked_at),default=None),'collection_errors':[{'source_id':s.id,'error':s.error[:240]} for s in linked if s.error],'article_count':sum(counts.get(s.id,0) for s in linked)})
    return {'items':rows[offset:offset+limit],'total':len(rows),'offset':offset,'limit':limit,'directory_total':len(SITES),'directory_media_total':sum(s['category']!='official' for s in SITES),'directory_official_total':sum(s['category']=='official' for s in SITES),'ranking':'curated_not_traffic_rank','discovery_checked':len(discoveries),'discovery_total':len(SITES),'discovery_active':sum(d.get('status')=='active' for d in discoveries.values()),'research_checked':len(probes),'research_reachable':sum(p.get('homepage_status')=='reachable' for p in probes.values()),'research_feed_found':sum(bool(p.get('feed_url')) for p in probes.values()),'archive_active_sites':sum(any(s.active for s in groups.get(site['domain'],[])) for site in SITES),'limitation':'Хэвлэл/мэдээллийн сайтын түүхэн бүртгэл ба тусдаа ангилсан албан эх сурвалжийн лавлах; өнөөгийн топ хандалтын эрэмбэ биш. Веб хайлт нь гаднын Google/Bing рүү шилжинэ. Архивын хайлт зөвхөн татсан нийтлэлд үйлчилнэ.'}
