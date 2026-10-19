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
