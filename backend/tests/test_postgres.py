"""Optional real PostgreSQL/pgvector tests in an isolated schema.
Requires an explicitly provided dedicated OPENWATCH_TEST_POSTGRES_URL.
"""
import os,uuid
import pytest
from sqlalchemy import create_engine,text,select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command
from app.config import settings
from app.models import Article,ArticleEmbedding,Source,Base
from app.collector import ingest
from app.clustering import rebuild_events

URL=os.environ.get('OPENWATCH_TEST_POSTGRES_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Dedicated PostgreSQL/pgvector URL not provided')

@pytest.fixture
def pg(monkeypatch):
    schema='ow_test_'+uuid.uuid4().hex
    admin=create_engine(URL)
    with admin.begin() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public'))
        conn.execute(text('CREATE SCHEMA '+schema))
    url=make_url(URL).update_query_dict({'options':'-csearch_path='+schema+',public'})
    monkeypatch.setattr(settings,'database_url',url.render_as_string(hide_password=False))
    command.upgrade(Config('alembic.ini'),'head')
    engine=create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        admin.dispose()

def test_real_migration_jsonb_hnsw_and_cosine(pg):
    with Session(pg) as db:
        source=Source(name='Dedicated test',endpoint='https://ikon.mn/rss');db.add(source);db.flush()
        ingest(db,source,[{'url':'https://ikon.mn/postgres-test','title':'PostgreSQL test','excerpt':'Dedicated fixture','published_at':None,'updated_at':None,'source_metadata':{'test':True}}])
        article=db.scalar(select(Article));db.add(ArticleEmbedding(article_id=article.id,text_hash=article.text_hash,model='bge-m3',vector=[1.0]+[0.0]*1023));db.commit()
        nearest=db.scalar(select(ArticleEmbedding).order_by(ArticleEmbedding.vector.cosine_distance([1.0]+[0.0]*1023)))
        assert nearest.article_id==article.id
        assert db.scalar(text("SELECT count(*) FROM pg_indexes WHERE schemaname=current_schema() AND indexname='ix_embedding_cosine'"))==1
        assert db.scalar(text("SELECT source_metadata->>'test' FROM articles"))=='true'
        rebuild_events(db);db.commit()

def test_real_advisory_lock_serializes_connections(pg):
    key=uuid.uuid4().int%(2**31-1)
    with pg.connect() as a,pg.connect() as b:
        assert a.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':key}) is True
        try:assert b.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':key}) is False
        finally:a.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':key})
