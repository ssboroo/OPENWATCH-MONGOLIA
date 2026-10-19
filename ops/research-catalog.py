#!/usr/bin/env python3
"""Bounded homepage research through environment transport; never activates collection.
Run with the backend venv. Output is a dated snapshot, NOT production feed validation.
"""
import argparse, concurrent.futures, json, re, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]

def probe(site,timeout):
    row={'domain':site['domain'],'checked_at':datetime.now(timezone.utc).isoformat(),'homepage_status':'unreachable','production_validated':False,'transport':'research_environment','feed_candidates':[]}
    try:
        req=urllib.request.Request(site['website_url'],headers={'User-Agent':'OpenWatch-Directory-Research/1.0'})
        with urllib.request.urlopen(req,timeout=timeout) as response:
            raw=response.read(131072);row['http_status']=response.status;row['resolved_url']=response.url
            if 'html' not in response.headers.get('Content-Type','').lower():
                row['homepage_status']='non_html';return row
        soup=BeautifulSoup(raw,'html.parser');title=soup.title.get_text(' ',strip=True)[:250] if soup.title else ''
        row['homepage_title']=title
        row['homepage_status']='blocked_or_placeholder' if re.search(r'just a moment|access denied|domain.*sale|parked|suspended|403 forbidden|404 not found',title,re.I) else 'reachable'
        for link in soup.select('link[href]'):
            url=urljoin(row['resolved_url'],link['href']);host=urlsplit(url).hostname or ''
            if urlsplit(url).scheme!='https' or host.removeprefix('www.')!=site['domain']:continue
            if 'icon' in ' '.join(link.get('rel',[])) and not row.get('icon_url'):row['icon_url']=url
            if any(t in link.get('type','') for t in ('rss','atom')) and '/comments/' not in url:row['feed_candidates'].append(url)
        row['feed_candidates']=list(dict.fromkeys(row['feed_candidates']))[:4]
    except Exception as exc:row['error']=type(exc).__name__+': '+str(exc)[:150]
    return row

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);p.add_argument('--workers',type=int,default=16);p.add_argument('--timeout',type=float,default=7);p.add_argument('--resume',action='store_true');args=p.parse_args()
    sites=json.loads((ROOT/'backend/app/data/mongolia-sites.v2.json').read_text());rows=[]
    output=Path(args.output)
    if args.resume and output.exists():
        domains={s['domain'] for s in sites}
        rows=[r for r in json.loads(output.read_text()) if r['domain'] in domains]
        checked={r['domain'] for r in rows}
        sites=[s for s in sites if s['domain'] not in checked]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max(args.workers,1),24)) as pool:
        futures=[pool.submit(probe,s,args.timeout) for s in sites]
        for future in concurrent.futures.as_completed(futures):
            rows.append(future.result())
            if len(rows)%25==0:
                output.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print('Checked',len(rows),flush=True)
    output.write_text(json.dumps(sorted(rows,key=lambda r:r['domain']),ensure_ascii=False,indent=2)+'\n')
    print('Complete',len(rows),'reachable',sum(r['homepage_status']=='reachable' for r in rows))
if __name__=='__main__':main()
