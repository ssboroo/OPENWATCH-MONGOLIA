"""Immutable report snapshots. Publishing always requires explicit human review."""
import hashlib
import json
from collections import defaultdict
from itertools import combinations
from sqlalchemy import select, func
from .models import Article, ArticleVersion, Event, EventArticle, Source, EvidenceItem, Claim, ClaimComparison, AnalysisRun, PublicReport, ReportCorrection, SimilarityMatch, now
from .config import settings
from .clustering import canonical_event, utc, publication_lock
from .evidence import privacy_flags, redact

FINDINGS={'verified_sources','sources_differ','needs_review','insufficient_evidence','correction_received','unclear'}
LIMITATIONS=[
    'Ижил агуулга, ойр нийтэлсэн цаг нь зохион байгуулалт, хамтын ажиллагаа эсвэл буруутай үйлдлийн нотолгоо биш.',
    'Хамрах хүрээ нь зөвхөн энэ системд бүртгэгдсэн нийтлэл. Хамгийн эрт бүртгэгдсэн нийтлэлийг анхны нийтлэгч гэж батлахгүй.',
    'Feed-ийн гарчиг ба богино агуулгыг шинжилсэн. Эх нийтлэлийн бүтэн агуулга, хараат бус албан баримтыг автоматаар баталгаажуулаагүй.',
    'Өөр тоо, огноо нь нөхцөл, нэгж, хугацааны ялгаанаас үүдэж болно. Зөрүүний нэр дэвшигч бүр хүний хяналт шаарддаг.'
]

def iso(value):return utc(value).isoformat() if value else None

def content_hash(body):
    return hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def build_report(db,event_id):
    publication_lock(db)
    event=canonical_event(db,event_id)
    if event is None:raise ValueError('Event not found')
    total=db.scalar(select(func.count()).select_from(EventArticle).where(EventArticle.event_id==event.id))
    articles=list(db.scalars(select(Article).join(EventArticle,EventArticle.article_id==Article.id).where(EventArticle.event_id==event.id).order_by(Article.id).limit(200).with_for_update(of=Article)))
    if not articles:raise ValueError('Event contains no articles')
    ids=[a.id for a in articles]
    versions=list(db.scalars(select(ArticleVersion).join(Article,ArticleVersion.article_id==Article.id).where(Article.id.in_(ids),ArticleVersion.version==Article.version)))
    version_ids=[v.id for v in versions]
    evidence=list(db.scalars(select(EvidenceItem).where(EvidenceItem.article_version_id.in_(version_ids)).order_by(EvidenceItem.id)))
    if not evidence:raise ValueError('Analyze articles before building a report')
    eids=[e.id for e in evidence]
    claims=list(db.scalars(select(Claim).where(Claim.evidence_id.in_(eids)).order_by(Claim.id)))
    grouped=defaultdict(list)
    for claim in claims:
        if claim.kind in {'money','percentage','quantity','date'}:
            grouped[(claim.kind,claim.unit,claim.context_key)].append(claim)
    discrepancies=[]
    for group in grouped.values():
        for left,right in combinations(group[:30],2):
            if left.article_id==right.article_id or left.value==right.value:continue
            a,b=sorted([left.id,right.id])
            comparison=db.scalar(select(ClaimComparison).where(ClaimComparison.left_claim_id==a,ClaimComparison.right_claim_id==b))
            if comparison is None:
                comparison=ClaimComparison(left_claim_id=a,right_claim_id=b);db.add(comparison);db.flush()
            discrepancies.append({'comparison_id':comparison.id,'left_claim_id':left.id,'right_claim_id':right.id,'left_evidence_id':left.evidence_id,'right_evidence_id':right.evidence_id,'values':[left.value,right.value],'kind':left.kind,'method':comparison.method,'confidence':comparison.confidence,'status':'human_review_required','limitation':comparison.limitation})
    runs=list(db.scalars(select(AnalysisRun).where(AnalysisRun.article_version_id.in_(version_ids)).order_by(AnalysisRun.id)))
    sources={s.id:s for s in db.scalars(select(Source).where(Source.id.in_({a.source_id for a in articles})))}
    matches=list(db.scalars(select(SimilarityMatch).where(SimilarityMatch.article_id.in_(ids),SimilarityMatch.other_id.in_(ids)).order_by(SimilarityMatch.id)))
    timeline=sorted(articles,key=lambda a:(a.published_at is None,utc(a.published_at or a.first_seen_at),a.id))
    earliest=min((utc(a.published_at) for a in articles if a.published_at),default=None)
    body={'schema_version':'report-v1','event_id':event.id,
        'scope':{'article_ids':ids,'article_version_ids':version_ids,'source_count':len(sources),'total_event_articles':total,'truncated':total>len(articles),'coverage':'only_observed_feed_excerpts','timezone':'UTC'},
        'sources':[{'id':s.id,'name':s.name,'endpoint':s.endpoint,'license':s.license,'permission_note':s.permission_note} for s in sorted(sources.values(),key=lambda s:s.id)],
        'articles':[{'id':a.id,'version':a.version,'title':a.title,'url':a.url,'source_id':a.source_id,'text_hash':a.text_hash} for a in articles],
        'timeline':[{'article_id':a.id,'url':a.url,'source_id':a.source_id,'published_at':iso(a.published_at),'feed_updated_at':iso(a.updated_at),'first_seen_at':iso(a.first_seen_at),'fetched_at':iso(a.fetched_at),'source_timezone':sources[a.source_id].timezone,'published_raw':a.source_metadata.get('published_raw'),'feed_updated_raw':a.source_metadata.get('updated_raw'),'minutes_after_earliest_observed_publication':round((utc(a.published_at)-earliest).total_seconds()/60,2) if a.published_at and earliest else None} for a in timeline],
        'matches':[{'article_ids':[m.article_id,m.other_id],'score':m.score,'method':m.method,'embedding_model':settings.embedding_model if m.method=='embedding_cosine' else None} for m in matches],
        'evidence':[{'id':e.id,'article_id':e.article_id,'article_version_id':e.article_version_id,'url':e.source_url,'quote':e.excerpt,'start':e.start_offset,'end':e.end_offset,'method':e.method,'confidence':e.confidence,'observed_at':iso(e.observed_at)} for e in evidence],
        'claims':[{'id':c.id,'article_id':c.article_id,'evidence_id':c.evidence_id,'kind':c.kind,'value':c.value,'unit':c.unit,'status':'unverified'} for c in claims],
        'discrepancies':discrepancies,
        'analysis':[{'id':r.id,'article_id':r.article_id,'article_version_id':r.article_version_id,'model':r.model,'embedding_model':r.result.get('embedding_model'),'prompt_version':r.prompt_version,'status':r.status,'summary_quotes':r.result.get('summary_quotes',[]),'confidence':r.confidence,'source_article_ids':[r.article_id],'evidence_urls':r.evidence_urls,'analyzed_at':iso(r.updated_at if r.status=='complete' else r.created_at),'limitation':r.limitation} for r in runs],
        'privacy_flags':sorted({flag for a in articles for flag in privacy_flags(a.title+' '+a.excerpt)}),
        'limitations':LIMITATIONS+(['Том үйл явдлын snapshot-д эхний 200 нийтлэлийг хамруулсан; бүх мэдээг хамарсан гэж үзэхгүй.'] if total>len(articles) else [])}
    h=content_hash(body)
    old=db.scalar(select(PublicReport).where(PublicReport.event_id==event.id).order_by(PublicReport.revision.desc()).limit(1))
    if old and old.body_hash==h:return old
    report=PublicReport(event_id=event.id,revision=(old.revision+1 if old else 1),title=event.title,body=body,body_hash=h,finding='sources_differ' if discrepancies else 'needs_review',state='draft')
    db.add(report);db.flush();return report

def build_changed_reports(db,article_ids):
    events=set(db.scalars(select(EventArticle.event_id).where(EventArticle.article_id.in_(article_ids))))
    reports=[]
    for event_id in sorted(events):
        try:reports.append(build_report(db,event_id).id)
        except ValueError:continue
    return reports

def public_report(db,report):
    # Snapshots are immutable; corrections are attached as reviewed annotations.
    def safe(value,key=''):
        if isinstance(value,str):return value if key in ('url','endpoint','evidence_urls') else redact(value)
        if isinstance(value,list):return [safe(v,key) for v in value]
        if isinstance(value,dict):return {k:safe(v,k) for k,v in value.items()}
        return value
    corrections=list(db.scalars(select(ReportCorrection).where(ReportCorrection.report_id==report.id,ReportCorrection.state=='accepted').order_by(ReportCorrection.id)))
    display_body=safe(report.body)
    return {'display_body_hash':content_hash(display_body),'id':report.id,'event_id':report.event_id,'revision':report.revision,'title':redact(report.title),'state':report.state,'finding':'correction_received' if report.correction_pending else report.finding,'body':display_body,'body_hash':report.body_hash,'created_at':report.created_at,'reviewed_at':report.reviewed_at,'review_note':redact(report.review_note or ''),'correction_pending':report.correction_pending,'corrections':[{'id':c.id,'text':redact(c.text),'evidence_urls':c.evidence_urls,'response':redact(c.response or ''),'reviewed_at':c.reviewed_at} for c in corrections]}
