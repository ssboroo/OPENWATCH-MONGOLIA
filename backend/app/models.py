from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Boolean, Integer, Float, UniqueConstraint, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

def now():
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class Source(Base):
    __tablename__ = 'sources'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    publisher: Mapped[str] = mapped_column(String(200), default='')
    kind: Mapped[str] = mapped_column(String(20), default='rss')
    timezone: Mapped[str] = mapped_column(String(80), default='Asia/Ulaanbaatar')
    license: Mapped[str] = mapped_column(Text, default='')
    permission_note: Mapped[str] = mapped_column(Text, default='')
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

class Article(Base):
    __tablename__ = 'articles'
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey('sources.id', ondelete='RESTRICT'), index=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    analysis_hash: Mapped[str | None] = mapped_column(String(64))
    ai_hash: Mapped[str | None] = mapped_column(String(100))
    next_analysis_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    version: Mapped[int] = mapped_column(default=1)
    analysis_status: Mapped[str] = mapped_column(String(40), default='lexical_only')
    rights_status: Mapped[str] = mapped_column(String(40), default='metadata_and_excerpt')
    source_metadata: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, 'postgresql'), default=dict)

class ArticleVersion(Base):
    __tablename__ = 'article_versions'
    source_id: Mapped[int | None] = mapped_column(ForeignKey('sources.id', ondelete='RESTRICT'))
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint('article_id', 'version'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'), index=True)
    version: Mapped[int]
    title: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Event(Base):
    __tablename__ = 'events'
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey('events.id', ondelete='SET NULL'), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=now)
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    limitation: Mapped[str] = mapped_column(Text, default='Ижил агуулга нь хамтын ажиллагаа, худал мэдээлэл, хууль бус үйлдлийн нотолгоо биш. Зөвхөн бүртгэгдсэн өгөгдлийн хүрээнд харьцуулсан.')

class EventArticle(Base):
    __tablename__ = 'event_articles'
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id', ondelete='CASCADE'), primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True)

class SimilarityMatch(Base):
    __tablename__ = 'similarity_matches'
    __table_args__ = (UniqueConstraint('article_id', 'other_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'))
    other_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'))
    score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(30))

class CollectionRun(Base):
    __tablename__ = 'collection_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default='running')
    added: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

# Phase 2–4: evidence always references an immutable article version.
from pgvector.sqlalchemy import VECTOR

class Entity(Base):
    __tablename__ = 'entities'
    __table_args__ = (UniqueConstraint('kind', 'normalized_name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(300))

class EvidenceItem(Base):
    __tablename__ = 'evidence_items'
    __table_args__ = (UniqueConstraint('article_version_id', 'start_offset', 'end_offset'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'), index=True)
    article_version_id: Mapped[int] = mapped_column(ForeignKey('article_versions.id', ondelete='CASCADE'), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int]
    end_offset: Mapped[int]
    method: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class EntityMention(Base):
    __tablename__ = 'entity_mentions'
    method: Mapped[str] = mapped_column(String(80),default='model_extractive_v1')
    confidence: Mapped[float] = mapped_column(Float,default=0.0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),default=now)
    __table_args__ = (UniqueConstraint('entity_id', 'evidence_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey('entities.id', ondelete='CASCADE'), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'), index=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('evidence_items.id', ondelete='CASCADE'))

class ArticleEmbedding(Base):
    __tablename__ = 'article_embeddings'
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True)
    text_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100), index=True)
    vector: Mapped[list] = mapped_column(VECTOR(1024).with_variant(JSON(), 'sqlite'))
    dimensions: Mapped[int] = mapped_column(default=1024)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AnalysisRun(Base):
    __tablename__ = 'analysis_runs'
    __table_args__ = (UniqueConstraint('article_version_id', 'model', 'prompt_version'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'), index=True)
    article_version_id: Mapped[int] = mapped_column(ForeignKey('article_versions.id', ondelete='CASCADE'))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), index=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    limitation: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Claim(Base):
    __tablename__ = 'claims'
    __table_args__ = (UniqueConstraint('evidence_id', 'kind', 'value'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'), index=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('evidence_items.id', ondelete='CASCADE'))
    kind: Mapped[str] = mapped_column(String(40), index=True)
    value: Mapped[str] = mapped_column(String(300))
    unit: Mapped[str] = mapped_column(String(80), default='')
    context_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(40), default='unverified')

class ClaimComparison(Base):
    __tablename__ = 'claim_comparisons'
    __table_args__ = (UniqueConstraint('left_claim_id', 'right_claim_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    left_claim_id: Mapped[int] = mapped_column(ForeignKey('claims.id', ondelete='CASCADE'))
    right_claim_id: Mapped[int] = mapped_column(ForeignKey('claims.id', ondelete='CASCADE'))
    relation: Mapped[str] = mapped_column(String(40), default='different_value_candidate')
    method: Mapped[str] = mapped_column(String(60), default='same_context_numeric_v1')
    confidence: Mapped[float] = mapped_column(Float, default=0.4)
    limitation: Mapped[str] = mapped_column(Text, default='Ижил өгүүлбэрийн хүрээнд өөр тоо дурдсан байж болзошгүй. Энэ нь худал мэдээлэл гэдгийг батлахгүй; хүний хяналт шаардлагатай.')

class PublicReport(Base):
    __tablename__ = 'public_reports'
    __table_args__ = (UniqueConstraint('event_id', 'revision'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id', ondelete='RESTRICT'), index=True)
    revision: Mapped[int]
    title: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default='draft', index=True)
    finding: Mapped[str] = mapped_column(String(40), default='needs_review')
    body: Mapped[dict] = mapped_column(JSON)
    body_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    privacy_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    correction_pending: Mapped[bool] = mapped_column(Boolean, default=False)

class ReportCorrection(Base):
    __tablename__ = 'report_corrections'
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey('public_reports.id', ondelete='CASCADE'), index=True)
    text: Mapped[str] = mapped_column(Text)
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(30), default='pending', index=True)
    response: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ArticleObservation(Base):
    __tablename__ = 'article_observations'
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id', ondelete='CASCADE'), index=True)
    state: Mapped[str] = mapped_column(String(30))
    http_status: Mapped[int | None]
    note: Mapped[str] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SystemState(Base):
    __tablename__ = 'system_state'
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ArticleBodyCheck(Base):
    __tablename__ = 'article_body_checks'
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id',ondelete='CASCADE'),primary_key=True)
    article_version_id: Mapped[int] = mapped_column(ForeignKey('article_versions.id',ondelete='CASCADE'),index=True)
    state: Mapped[str] = mapped_column(String(30),index=True)
    body_hash: Mapped[str | None] = mapped_column(String(64),index=True)
    data: Mapped[dict] = mapped_column(JSON().with_variant(JSONB,'postgresql'),default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
