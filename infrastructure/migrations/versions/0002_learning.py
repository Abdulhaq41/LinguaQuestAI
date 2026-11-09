"""Assessment, spaced repetition and game mechanics.
Revision ID: 0002
"""
from alembic import op
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    from infrastructure.migrations.schema_0002 import metadata
    metadata.create_all(bind=op.get_bind(),tables=[metadata.tables[x] for x in ['assessments','user_vocabulary','vocabulary_reviews','user_achievements','cosmetic_purchases','simulation_progress','referrals','notifications']])

def downgrade():raise RuntimeError('Restore verified backup rather than destroying progress')
