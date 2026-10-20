"""Human-labelled exact-body benchmark, pinned to article/body versions."""
from sqlalchemy import select
from .models import SystemState,now,Article
from .body_checks import compare_archive

def summary(db):
    rows=[s.value for s in db.scalars(select(SystemState).where(SystemState.name.like('quality:%')))]
    tp=sum(r['expected'] and r['predicted'] for r in rows);fp=sum(not r['expected'] and r['predicted'] for r in rows)
    fn=sum(r['expected'] and not r['predicted'] for r in rows);tn=sum(not r['expected'] and not r['predicted'] for r in rows)
    return {'status':'reviewed_sample' if rows else 'awaiting_human_review','reviewed_pairs':len(rows),'true_positive':tp,'false_positive':fp,'true_negative':tn,'false_negative':fn,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,'limitation':'Зөвхөн хүний хянасан энэ түүврийн яг ижил үндсэн эхийн хэмжилт. Нийт системийн үнэн зөвийн хувь биш; шүүгч таамаглалаас хараат бусаар хянах шаардлагатай.'}

def review(db,left,right,expected,note):
    if left==right:raise ValueError('Choose distinct articles')
    a,b=db.get(Article,left),db.get(Article,right)
    if not a or not b:raise ValueError('Article not found')
    data=compare_archive(db,a,right);match=data['items'][0]
    if data['body']['state']!='ready' or match['body']['state']!='ready':raise ValueError('Both current article bodies must be readable')
    ids=sorted([(a.id,data['body']['version_id'],data['body']['body_hash']),(b.id,match['body']['version_id'],match['body']['body_hash'])])
    import hashlib,json
    name='quality:'+hashlib.sha256(json.dumps(ids).encode()).hexdigest()
    row=db.get(SystemState,name)
    if row is None:row=SystemState(name=name);db.add(row)
    row.value={'article_ids':[left,right],'versions':ids,'expected':expected,'predicted':match['comparison']=='normalized_body_equal','note':note,'reviewed_at':now().isoformat()};row.updated_at=now();db.flush()
    return summary(db)
