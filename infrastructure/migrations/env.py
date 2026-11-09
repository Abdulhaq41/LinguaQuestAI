from alembic import context
from services.api.db import engine, Base
from services.api import models

def run():
    with engine.connect() as conn:
        context.configure(connection=conn,target_metadata=Base.metadata,render_as_batch=engine.dialect.name=='sqlite')
        with context.begin_transaction():context.run_migrations()
run()
