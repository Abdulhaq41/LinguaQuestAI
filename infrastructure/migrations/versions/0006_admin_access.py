"""Audited gift access and administration. Existing paid records are preserved."""
from alembic import op
import sqlalchemy as sa
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('users',sa.Column('is_blocked',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('users',sa.Column('block_reason',sa.String(500),nullable=True))
    op.create_table('access_grants',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('user_id',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False,index=True),
        sa.Column('plan_id',sa.String(20),sa.ForeignKey('subscription_plans.id'),nullable=False),
        sa.Column('created_by',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('reason',sa.String(500),nullable=False),
        sa.Column('starts_at',sa.BigInteger(),nullable=False),
        sa.Column('expires_at',sa.BigInteger(),nullable=False,index=True),
        sa.Column('created_at',sa.BigInteger(),nullable=False),
        sa.Column('revoked_at',sa.BigInteger(),nullable=True),
        sa.Column('revoked_by',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=True),
        sa.Column('revoke_reason',sa.String(500),nullable=True))
    op.create_table('admin_audit_logs',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('actor_id',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False,index=True),
        sa.Column('target_id',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=True,index=True),
        sa.Column('action',sa.String(80),nullable=False,index=True),
        sa.Column('details',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.BigInteger(),nullable=False,index=True))
    op.create_table('app_settings',
        sa.Column('key',sa.String(80),primary_key=True),
        sa.Column('value',sa.JSON(),nullable=False),
        sa.Column('updated_by',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('updated_at',sa.BigInteger(),nullable=False))

def downgrade():raise RuntimeError('Restore a verified backup rather than deleting the access ledger')
