from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

class Base(DeclarativeBase):
    pass

url = settings().database_url
engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {}, pool_pre_ping=True)
if url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_pragmas(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA journal_mode=WAL')
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as db:
        # SQLite is a local development option. Serialize transactions as row locks are unavailable.
        if url.startswith('sqlite'):
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
