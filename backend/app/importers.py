"""Bounded explicit open-data formats. No full article scraping or access bypass."""
import csv
import io
import json
from itertools import islice
from datetime import datetime,timezone
from urllib.parse import urlsplit
from defusedxml import ElementTree
from .collector import canonical, clean, parse_feed

def timestamp(value):
    if not value:return None
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Imported timestamps require an explicit timezone')
    return parsed.astimezone(timezone.utc)

def records(rows,kind):
    result=[]
    if not isinstance(rows,list) or len(rows)>500:raise ValueError('Expected at most 500 records')
    for row in rows:
        if not isinstance(row,dict) or not row.get('url') or not row.get('title'):raise ValueError('Each record requires title and url')
        result.append({'url':canonical(str(row['url'])),'title':clean(str(row['title']))[:1000],'excerpt':clean(str(row.get('summary','')))[:600],'published_at':timestamp(row.get('published_at')),'updated_at':timestamp(row.get('updated_at')),'source_metadata':{'format':kind}})
    return result

def parse_source(raw,kind='rss',endpoint=''):
    if len(raw)>2_000_000:raise ValueError('Import exceeds size limit')
    if kind in ('rss','atom'):return parse_feed(raw)
    if kind=='json':
        data=json.loads(raw)
        return records(data.get('items') if isinstance(data,dict) else data,'json')
    if kind=='csv':
        data=list(islice(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))),501))
        return records(data,'csv')
    if kind=='sitemap':
        root=ElementTree.fromstring(raw)
        if root.tag.rsplit('}',1)[-1]!='urlset':raise ValueError('Only urlset sitemaps supported; register sitemap index children explicitly')
        rows=[];host=(urlsplit(endpoint).hostname or '').removeprefix('www.')
        for node in list(root)[:500]:
            values={c.tag.rsplit('}',1)[-1]:(c.text or '') for c in node}
            url=canonical(values.get('loc',''))
            if (urlsplit(url).hostname or '').removeprefix('www.')!=host:raise ValueError('Cross-domain sitemap URL rejected')
            rows.append({'url':url,'title':'[Гарчиг татаагүй] '+urlsplit(url).path[-120:],'excerpt':'','published_at':None,'updated_at':timestamp(values.get('lastmod')) if 'T' in values.get('lastmod','') else None,'source_metadata':{'format':'sitemap','metadata_only':True,'sitemap_lastmod_raw':values.get('lastmod','')[:200]}})
        return rows
    raise ValueError('Unsupported source kind')
