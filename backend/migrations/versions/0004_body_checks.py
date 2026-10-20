"""Derived article body fingerprints; full publisher text is not retained."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0004_body_checks'
down_revision='0003_provenance'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('article_body_checks',sa.Column('article_id',sa.Integer(),sa.ForeignKey('articles.id',ondelete='CASCADE'),primary_key=True),sa.Column('article_version_id',sa.Integer(),sa.ForeignKey('article_versions.id',ondelete='CASCADE'),nullable=False),sa.Column('state',sa.String(30),nullable=False),sa.Column('body_hash',sa.String(64)),sa.Column('data',sa.JSON().with_variant(JSONB,'postgresql'),nullable=False),sa.Column('checked_at',sa.DateTime(timezone=True),nullable=False))
    for name in ('article_version_id','state','body_hash'):op.create_index('ix_article_body_checks_'+name,'article_body_checks',[name])

def downgrade():op.drop_table('article_body_checks')
