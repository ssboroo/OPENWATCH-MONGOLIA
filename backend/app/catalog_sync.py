"""Run on the VPS: discover and validate public feeds without auto-activation.
Usage: python -m app.catalog_sync [--domain ikon.mn]
The versioned directory is the explicit hostname allowlist for this command.
"""
import argparse
import asyncio
import json
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from sqlalchemy import select
from .catalog import SITES, probe_results, BY_DOMAIN
from .config import settings
from .security import download, fetch_feed
from .collector import parse_feed
from .models import Source, AuditLog, now
from .db import Session

async def sync(domain=None):
    sites=[BY_DOMAIN[domain]] if domain else SITES
    # Narrow to catalog domains, not arbitrary external redirects.
    allowed={host for site in sites for host in (site['domain'],'www.'+site['domain'])}
    # Catalog hostnames are already an explicit security allowlist; do not mutate process configuration.
    probes=probe_results()
    result=[]
    for site in sites:
        candidates=[]
        probe=probes.get(site['domain'],{})
        if probe.get('feed_url'):candidates.append(probe['feed_url'])
        candidates.extend(probe.get('feed_candidates',[]))
        try:
            # A homepage is only parsed for explicit rel=alternate feed discovery.
            raw=await fetch_feed(site['website_url'])
            soup=BeautifulSoup(raw,'html.parser')
            for tag in soup.select('link[href]'):
                if any(t in tag.get('type','').lower() for t in ('rss','atom')):
                    candidate=urljoin(site['website_url'],tag['href'])
                    if '/comments/' not in candidate:candidates.append(candidate)
        except Exception as exc:
            result.append({'domain':site['domain'],'stage':'homepage','error':type(exc).__name__+': '+str(exc)[:200]})
        for endpoint in list(dict.fromkeys(candidates))[:4]:
            if urlsplit(endpoint).hostname not in allowed:continue
            try:
                parsed=parse_feed(await fetch_feed(endpoint))
                with Session() as db:
                    source=db.scalar(select(Source).where(Source.endpoint==endpoint))
                    if source is None:
                        source=Source(name=site['name'],endpoint=endpoint,publisher=site['name'],active=False)
                        db.add(source)
                    source.validated_at=now();source.checked_at=now();source.error=None
                    db.add(AuditLog(action='catalog.feed.validate',detail=endpoint));db.commit()
                    result.append({'domain':site['domain'],'feed':endpoint,'entries':len(parsed),'source_id':source.id,'active':source.active,'status':'validated'})
                break
            except Exception as exc:
                result.append({'domain':site['domain'],'feed':endpoint,'status':'failed','error':type(exc).__name__+': '+str(exc)[:200]})
        await asyncio.sleep(1)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain',choices=sorted(BY_DOMAIN))
    args=parser.parse_args()
    asyncio.run(sync(args.domain))
