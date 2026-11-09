"""Persist initial recurring charge identity independent of delivery order.
Revision ID: 0003
"""
from alembic import op
import sqlalchemy as sa
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('orders',sa.Column('initial_charge_id',sa.String(255),nullable=True))
    op.add_column('orders',sa.Column('subscription_canceled',sa.Boolean(),nullable=False,server_default=sa.false()))

def downgrade():raise RuntimeError('Restore backup instead of removing billing identity')
