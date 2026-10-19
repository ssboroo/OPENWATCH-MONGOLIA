import hashlib
import re
from sqlalchemy import select
from .models import EvidenceItem, Claim, Entity, EntityMention, ArticleVersion

PRIVATE_PATTERNS=[re.compile(r'\b[А-ЯӨҮа-яөү]{2}\d{8}\b'),re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),re.compile(r'(?<!\d)(?:\+976[ -]?)?[689]\d{7}(?!\d)')]

def redact(text):
    for pattern in PRIVATE_PATTERNS:text=pattern.sub('[ХУВИЙН МЭДЭЭЛЭЛ НУУСАН]',text)
    return text

def privacy_flags(text):
    return [f'pattern_{i+1}' for i,p in enumerate(PRIVATE_PATTERNS) if p.search(text)]

def full_text(version):
    return version.title+'\n'+version.excerpt

def evidence_for(db,article,version,quote,method='extractive_v1',confidence=1.0):
    text=full_text(version)
    start=text.find(quote)
    if start<0 or not quote:raise ValueError('Evidence must match archived text exactly')
    end=start+len(quote)
    row=db.scalar(select(EvidenceItem).where(EvidenceItem.article_version_id==version.id,EvidenceItem.start_offset==start,EvidenceItem.end_offset==end))
    if row is None:
        row=EvidenceItem(article_id=article.id,article_version_id=version.id,source_url=article.url,excerpt=quote,start_offset=start,end_offset=end,method=method,confidence=confidence)
        db.add(row);db.flush()
    return row

def context_key(quote):
    normalized=re.sub(r'\d+(?:[.,]\d+)*',' <number> ',quote.casefold())
    normalized=' '.join(re.findall(r'\w+|<number>',normalized))
    return hashlib.sha256(normalized.encode()).hexdigest()

def add_claim(db,article,version,kind,value,quote,unit='',method='regex_v1'):
    if value not in quote:raise ValueError('Claim value missing from evidence')
    ev=evidence_for(db,article,version,quote,method)
    old=db.scalar(select(Claim).where(Claim.evidence_id==ev.id,Claim.kind==kind,Claim.value==value))
    if old:return old
    claim=Claim(article_id=article.id,evidence_id=ev.id,kind=kind,value=value[:300],unit=unit,context_key=context_key(quote),status='unverified')
    db.add(claim);db.flush();return claim

PATTERNS=[('date',re.compile(r'\b(?:19|20)\d{2}[-./]\d{1,2}[-./]\d{1,2}\b')),('percentage',re.compile(r'\b\d+(?:[.,]\d+)?\s*(?:%|хувь)')),('money',re.compile(r'\b\d+(?:[.,]\d+)*\s*(?:(?:мянга|сая|тэрбум|их наяд)\s*)?(?:төгрөг|₮|ам\.доллар|USD|MNT|доллар)(?!\w)',re.I)),('quantity',re.compile(r'\b\d+(?:[.,]\d+)?\s*(?:хүн|ширхэг|тонн|км|метр|ажилтан)\b'))]

def lexical_claims(db,article,version):
    text=full_text(version)
    for sentence in re.split(r'(?<=[!?。])\s+|\n|(?<=\.)\s+(?=[А-ЯӨҮA-Z])',text):
        sentence=sentence.strip()
        if not sentence or len(sentence)>1000:continue
        for kind,pattern in PATTERNS:
            for match in pattern.finditer(sentence):
                if privacy_flags(match.group()):continue
                unit=re.sub(r'[\d.,\s]+','',match.group()).casefold()
                add_claim(db,article,version,kind,match.group(),sentence,unit)
    # Quoted words are source statements, never independently verified facts.
    for m in re.finditer(r'[“"]([^”"\n]{10,250})[”"]',text):
        add_claim(db,article,version,'quote',m.group(1),m.group())

def add_entity(db,article,version,kind,name,quote,confidence=.5):
    if name not in quote or privacy_flags(name):return None
    normalized=' '.join(name.casefold().split())
    entity=db.scalar(select(Entity).where(Entity.kind==kind,Entity.normalized_name==normalized))
    if entity is None:
        entity=Entity(kind=kind,name=name,normalized_name=normalized);db.add(entity);db.flush()
    ev=evidence_for(db,article,version,quote,'model_extractive_v1',confidence)
    if not db.scalar(select(EntityMention).where(EntityMention.entity_id==entity.id,EntityMention.evidence_id==ev.id)):
        db.add(EntityMention(entity_id=entity.id,article_id=article.id,evidence_id=ev.id,method='model_extractive_v1',confidence=confidence))
    return entity
