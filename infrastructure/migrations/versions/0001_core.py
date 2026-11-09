"""Initial transactional learning and billing schema.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    # Metadata is frozen for revision 0001 in the adjacent schema module.
    from infrastructure.migrations.schema_0001 import metadata
    metadata.create_all(bind=op.get_bind())
    plans=sa.table('subscription_plans',sa.column('id',sa.String),sa.column('stars',sa.Integer),sa.column('enabled',sa.Boolean))
    op.bulk_insert(plans,[{'id':'START','stars':89,'enabled':True},{'id':'PRO','stars':149,'enabled':True},{'id':'ULTRA','stars':299,'enabled':True}])

def downgrade():
    raise RuntimeError('Destructive downgrade disabled. Restore a verified backup instead.')
