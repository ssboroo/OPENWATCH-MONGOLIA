"""Retain per-version feed provenance, including sitemap-to-feed upgrades."""
from alembic import op
import sqlalchemy as sa
revision='0003_provenance'
down_revision='0002_evidence'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('entity_mentions',sa.Column('method',sa.String(80),nullable=False,server_default='model_extractive_v1'))
    op.add_column('entity_mentions',sa.Column('confidence',sa.Float(),nullable=False,server_default='0'))
    op.add_column('entity_mentions',sa.Column('created_at',sa.DateTime(timezone=True),nullable=True))
    op.execute('UPDATE entity_mentions SET created_at=CURRENT_TIMESTAMP')
    op.execute('ALTER TABLE article_versions ADD COLUMN source_id INTEGER CONSTRAINT fk_versions_source REFERENCES sources(id) ON DELETE RESTRICT')
    op.add_column('article_versions',sa.Column('source_metadata',sa.JSON(),nullable=False,server_default=sa.text("'{}'")))
    op.execute('UPDATE article_versions SET source_id=(SELECT source_id FROM articles WHERE articles.id=article_versions.article_id)')

def downgrade():
    op.drop_column('entity_mentions','created_at')
    op.drop_column('entity_mentions','confidence')
    op.drop_column('entity_mentions','method')
    if op.get_bind().dialect.name=='postgresql':op.drop_constraint('fk_versions_source','article_versions',type_='foreignkey')
    op.drop_column('article_versions','source_metadata')
    op.drop_column('article_versions','source_id')
