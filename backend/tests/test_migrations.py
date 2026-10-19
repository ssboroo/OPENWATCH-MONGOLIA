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
