from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect
from app.config import settings

def test_upgrade_downgrade(tmp_path,monkeypatch):
    url=f'sqlite:///{tmp_path}/migration.db'
    monkeypatch.setattr(settings,'database_url',url)
    config=Config('alembic.ini')
    command.upgrade(config,'head')
    engine=create_engine(url)
    assert {'sources','articles','article_versions','events','event_articles','similarity_matches','collection_runs','audit_logs'} <= set(inspect(engine).get_table_names())
    command.downgrade(config,'base')
    assert 'articles' not in inspect(engine).get_table_names()
    engine.dispose()

def test_upgrade_preserves_existing_archive_and_backfills_provenance(tmp_path,monkeypatch):
    from sqlalchemy import text
    from app.models import Source
    from sqlalchemy.orm import Session
    url=f'sqlite:///{tmp_path}/legacy.db'
    monkeypatch.setattr(settings,'database_url',url)
    config=Config('alembic.ini');command.upgrade(config,'0001_archive')
    engine=create_engine(url)
    with Session(engine) as db:
        db.add(Source(name='[DEMO] migration fixture',endpoint='https://ikon.mn/rss'));db.commit()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO articles (id,source_id,url,title,excerpt,text_hash,first_seen_at,fetched_at,version,analysis_status,rights_status,source_metadata) VALUES (1,1,'https://ikon.mn/test','[DEMO] title','fixture',:hash,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1,'lexical_only','metadata_and_excerpt','{}')"),{'hash':'0'*64})
        conn.execute(text("INSERT INTO article_versions (id,article_id,version,title,excerpt,text_hash,observed_at) VALUES (1,1,1,'[DEMO] title','fixture',:hash,CURRENT_TIMESTAMP)"),{'hash':'0'*64})
        conn.execute(text("INSERT INTO events (id,title,first_seen_at,limitation) VALUES (1,'[DEMO]',CURRENT_TIMESTAMP,'fixture')"))
        conn.execute(text('INSERT INTO event_articles (event_id,article_id) VALUES (1,1)'))
    command.upgrade(config,'head')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM articles'))==1
        assert conn.scalar(text('SELECT source_id FROM article_versions'))==1
        assert conn.scalar(text('SELECT count(*) FROM event_articles'))==1
    command.downgrade(config,'0001_archive')
    with engine.connect() as conn:assert conn.scalar(text('SELECT count(*) FROM articles'))==1
    engine.dispose()
