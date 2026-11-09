"""Quarantine late overlapping charges and queue automatic refunds.
Revision ID: 0004
"""
from alembic import op
import sqlalchemy as sa
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('payments',sa.Column('grants_access',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.add_column('payments',sa.Column('refund_pending',sa.Boolean(),nullable=False,server_default=sa.false()))

def downgrade():raise RuntimeError('Restore backup rather than removing reconciliation state')
