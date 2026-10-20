from datetime import timedelta
from app.models import Source,Article,now
from app.reliability import reliability
from app.config import settings
from app.catalog import directory

def test_unknown_backup_and_ai_progress_are_not_healthy(db,monkeypatch):
    monkeypatch.setattr(settings,'ai_enabled',True)
    s=Source(name='Ikon',endpoint='https://ikon.mn/rss',active=True,checked_at=now(),success_at=now()-timedelta(days=2),error='Timeout');db.add(s);db.flush()
    a=Article(source_id=s.id,url='https://ikon.mn/n/test',title='Төсөв',excerpt='Төсвийн мэдээ',text_hash='a'*64,next_analysis_at=now()+timedelta(hours=1));db.add(a);db.commit()
    r=reliability(db)
    assert r['queue']['pending']==1 and r['queue']['retry_wait']==1
    assert r['queue']['progress_stalled'] is True
    assert r['backup']['status']=='unverified'
    assert r['quality']['precision'] is None
    assert any(x['code']=='source_degraded' for x in r['alerts'])
    site=next(x for x in directory(db,limit=1000)['items'] if x['domain']=='ikon.mn')
    assert site['article_count']==1 and site['collection_errors'][0]['error']=='Timeout'
    assert site['last_checked_at'] is not None

def test_ai_disabled_has_no_false_backlog(db,monkeypatch):
    monkeypatch.setattr(settings,'ai_enabled',False)
    assert reliability(db)['queue']['pending']==0

def test_quality_metrics_require_real_labels(db):
    from app.quality import summary
    from app.models import SystemState
    assert summary(db)['precision'] is None
    for i,(expected,predicted) in enumerate([(True,True),(False,True),(True,False),(False,False)]):
        db.add(SystemState(name=f'quality:{i}',value={'expected':expected,'predicted':predicted}))
    db.commit();r=summary(db)
    assert r['reviewed_pairs']==4 and r['precision']==.5 and r['recall']==.5

def test_quality_rejects_unread_pairs(db):
    import pytest
    from app.quality import review
    s=Source(name='test',endpoint='https://ikon.mn/rss');db.add(s);db.flush()
    for i in range(2):db.add(Article(source_id=s.id,url=f'https://ikon.mn/{i}',title='Мэдээ',excerpt='',text_hash=str(i)*64))
    db.commit()
    with pytest.raises(ValueError,match='readable'):review(db,1,2,True,'Human reviewer: test note')
