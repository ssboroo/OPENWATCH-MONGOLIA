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
    if kind=='html':return parse_headlines(raw,endpoint)
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
            news=next((c for c in node if c.tag.rsplit('}',1)[-1]=='news'),None)
            title=next(((c.text or '') for c in list(news) if c.tag.rsplit('}',1)[-1]=='title'),'') if news is not None else ''
            rows.append({'url':url,'title':clean(title)[:1000] if title else '[Гарчиг татаагүй] '+urlsplit(url).path[-120:],'excerpt':'','published_at':None,'updated_at':timestamp(values.get('lastmod')) if 'T' in values.get('lastmod','') else None,'source_metadata':{'format':'sitemap','metadata_only':True,'sitemap_has_title':bool(title),'sitemap_lastmod_raw':values.get('lastmod','')[:200]}})
        return rows
    raise ValueError('Unsupported source kind')

def parse_headlines(raw, endpoint):
    """Publisher's public headline links only; no article-body scraping."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin,parse_qs
    import re
    soup=BeautifulSoup(raw,'html.parser')
    for tag in soup.select('script,style,nav,header,footer,form,aside,noscript'):tag.decompose()
    host=(urlsplit(endpoint).hostname or '').removeprefix('www.')
    rows=[];seen=set()
    selectors='article a[href],h1 a[href],h2 a[href],h3 a[href],a[href]:has(h2),a[href]:has(h3),a[class*="title"][href],a[class*="headline"][href]'
    selected=list(soup.select(selectors))
    # Some publishers (e.g. iKon) use plain anchors, with article IDs in the URL.
    for tag in soup.select('a[href]'):
        path=urlsplit(urljoin(endpoint,tag['href'])).path
        if re.search(r'^/(?:n|r|lr|z|a|p|news|newsDetail|news-detail|article|articles|post|posts)/[^/]+|^/\d{3,}/?$',path,re.I):
            selected.append(tag)
        elif path=='/index.php' and re.fullmatch(r'[1-9][0-9]{0,9}',parse_qs(urlsplit(urljoin(endpoint,tag['href'])).query).get('newsid',[''])[0]):
            selected.append(tag)
    for tag in selected:
        heading=tag.find(['h1','h2','h3'])
        if heading is None and 'post-link' in tag.get('class',[]):
            card=tag.find_parent(class_='post-item')
            if card is not None:heading=card.select_one('.post-title')
        title=clean((heading or tag).get_text(' ',strip=True))
        if len(title)<24 or len(title)>500 or len(title.split())<3:continue
        target=urlsplit(urljoin(endpoint,tag['href']))
        if target.scheme=='http' and target.hostname and target.hostname.removeprefix('www.')==host and target.port is None:
            target=target._replace(scheme='https')
        try:url=canonical(target.geturl())
        except ValueError:continue
        u=urlsplit(url)
        if u.scheme!='https' or (u.hostname or '').removeprefix('www.')!=host or u.path in ('','/'):continue
        if re.search(r'/(?:category|tag|author|search|login|register|page)(?:/|$)',u.path,re.I):continue
        if url in seen:continue
        seen.add(url)
        rows.append({'url':url,'title':title,'excerpt':'','published_at':None,'updated_at':None,'source_metadata':{'format':'html','metadata_only':True,'headline_only':True}})
        if len(rows)>=80:break
    if len(rows)<3:raise ValueError('No reliable public headline list found')
    return rows
