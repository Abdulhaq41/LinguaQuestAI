import os
os.environ['APP_ENV']='development'
os.environ['ENABLE_DEV_AUTH']='true'
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from services.api.db import Base,get_db
from services.api.models import Plan
from services.api.main import app,limits

@pytest.fixture
def db(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'test.db'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    Factory=sessionmaker(engine,expire_on_commit=False)
    with Factory() as session:
        session.add_all([Plan(id='START',stars=89),Plan(id='PRO',stars=149),Plan(id='ULTRA',stars=299)])
        session.commit()
    with Factory() as session:yield session
    engine.dispose()

@pytest.fixture
def client(db):
    limits.clear()
    def dependency():
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
    app.dependency_overrides[get_db]=dependency
    with TestClient(app) as client:yield client
    app.dependency_overrides.clear()

@pytest.fixture
def member(client):
    assert client.post('/api/auth/dev').status_code==200
    assert client.patch('/api/users/me/settings',json={}).status_code==200
    return client
