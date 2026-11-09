"""Versioned content and immutable attempt snapshots.
Revision ID: 0005
"""
from alembic import op
import sqlalchemy as sa
revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('lesson_attempts',sa.Column('content_snapshot',sa.JSON(),nullable=True))
    op.create_table('content_versions',sa.Column('id',sa.String(36),primary_key=True),sa.Column('lesson_id',sa.String(80),nullable=False,index=True),sa.Column('version',sa.Integer(),nullable=False),sa.Column('content',sa.JSON(),nullable=False),sa.Column('admin_id',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.Integer(),nullable=False),sa.UniqueConstraint('lesson_id','version'))

def downgrade():raise RuntimeError('Restore backup rather than losing content versions')
