"""Read public Next.js transport data as JSON, never execute publisher scripts.

GoGo's current page renders article content on the client from public Flight
records. Only a title-matched news object's own text blocks are accepted; menu,
related news and arbitrary script strings cannot become an article body.
"""
import json,re
from bs4 import BeautifulSoup

MAX_BYTES=2_000_000

def next_records(soup):
    chunks=[];decoder=json.JSONDecoder();size=0
    for tag in soup.select('script')[:150]:
        script=tag.string or tag.get_text();start=0
        for _ in range(20):
            at=script.find('self.__next_f.push(',start)
            if at<0:break
            start=at+len('self.__next_f.push(')
            try:row,used=decoder.raw_decode(script[start:])
            except (ValueError,RecursionError):break
            start+=used
            if isinstance(row,list) and len(row)==2 and row[0]==1 and isinstance(row[1],str):
                encoded=row[1].encode('utf-8');size+=len(encoded)
                if size>MAX_BYTES:return [],{}
                chunks.append(encoded)
    data=b''.join(chunks);texts={};masked=bytearray(data)
    for m in re.finditer(rb'(?:^|\n)([0-9a-f]{1,12}):T([0-9a-f]{1,8}),',data):
        length=int(m.group(2),16);end=m.end()+length
        if length>MAX_BYTES or end>len(data):continue
        try:texts[m.group(1).decode()]=data[m.end():end].decode('utf-8')
        except UnicodeDecodeError:continue
        masked[m.start():end]=b'\n'+b' '*(end-m.start()-2)+b'\n'
    records=[]
    for line in bytes(masked).splitlines()[:2000]:
        _,sep,payload=line.partition(b':')
        if not sep:continue
        try:records.append(json.loads(payload))
        except (ValueError,RecursionError):pass
    return records,texts

def gogo_body(soup,expected_title,normalize):
    if len(expected_title.split())<4:return None
    expected=normalize(expected_title).rstrip('.…')
    records,texts=next_records(soup);stack=list(records);examined=0
    while stack and examined<10000:
        row=stack.pop();examined+=1
        if isinstance(row,list):stack.extend(row[:500]);continue
        if not isinstance(row,dict):continue
        title=normalize(str(row.get('title',''))).rstrip('.…')
        content=row.get('content')
        if title and (title==expected or (len(expected)>=30 and title.startswith(expected))) and isinstance(content,list) and row.get('id') is not None:
            parts=[]
            for block in content[:100]:
                if not isinstance(block,dict) or block.get('conttype')!=0 or block.get('newsId')!=row['id']:continue
                value=block.get('body')
                if not isinstance(value,str):continue
                if re.fullmatch(r'\$[0-9a-f]{1,12}',value):value=texts.get(value[1:],'')
                # Treat a missing/truncated text reference as incomplete, never full equality.
                if not value:return None
                fragment=BeautifulSoup(value,'html.parser')
                for tag in fragment.select('script,style,nav,form,aside'):tag.decompose()
                text=fragment.get_text(' ',strip=True)
                if text:parts.append(text)
            if parts:return ' '.join(parts)
        stack.extend(v for v in row.values() if isinstance(v,(list,dict)))
    return None
