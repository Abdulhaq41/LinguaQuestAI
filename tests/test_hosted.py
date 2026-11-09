from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.api.config import Settings, settings
from services.api.hosted import attach_frontend, configure_telegram, DEPLOYMENT

@pytest.mark.parametrize('url,expected', [
    ('postgres://user:example@db/test','postgresql+psycopg://user:example@db/test'),
    ('postgresql://user:example@db/test','postgresql+psycopg://user:example@db/test'),
    ('postgresql+psycopg://user:example@db/test','postgresql+psycopg://user:example@db/test'),
    ('sqlite:///test.db','sqlite:///test.db'),
])
def test_paas_database_driver(url,expected):
    assert Settings(_env_file=None,database_url=url).database_url==expected

def test_frontend_and_api_share_origin(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTO_CONFIGURE_BOT','false')
    (tmp_path/'index.html').write_text('<h1>LinguaQuest</h1>')
    (tmp_path/'logo.svg').write_text('<svg/>')
    app=FastAPI()
    @app.get('/api/check')
    def check():return {'ok':True}
    with TestClient(attach_frontend(app,tmp_path)) as client:
        assert client.get('/').text=='<h1>LinguaQuest</h1>'
        assert client.get('/api/check').json()=={'ok':True}
        assert client.get('/logo.svg').status_code==200
        assert client.get('/../content/lessons/first-hello.json').status_code==404
        assert client.get('/api/unknown').status_code==404
        assert "frame-ancestors" in client.get('/').headers['content-security-policy']

def test_missing_build_fails_explicitly(tmp_path):
    with pytest.raises(RuntimeError,match='build is missing'):
        attach_frontend(FastAPI(),tmp_path)

@pytest.mark.asyncio
async def test_configures_only_expected_test_bot(monkeypatch):
    cfg=settings()
    for k,v in {'bot_token':'synthetic-test-placeholder','bot_username':'Linguaquesttest_bot','webapp_url':'https://example.test','webhook_secret':'test-placeholder-'*4}.items():
        monkeypatch.setattr(cfg,k,v)
    remote=AsyncMock(side_effect=[{'username':'Linguaquesttest_bot'},True,True,True])
    monkeypatch.setattr('services.api.hosted.telegram',remote)
    await configure_telegram()
    assert DEPLOYMENT['telegram']=='ready'
    methods=[c.args[0] for c in remote.call_args_list]
    assert methods==['getMe','setWebhook','setChatMenuButton','setMyCommands']
    assert remote.call_args_list[1].kwargs['drop_pending_updates'] is False
    assert remote.call_args_list[1].kwargs['url']=='https://example.test/api/telegram/webhook'

@pytest.mark.asyncio
async def test_wrong_bot_never_reconfigured(monkeypatch):
    cfg=settings()
    for k,v in {'bot_token':'synthetic-test-placeholder','bot_username':'Linguaquesttest_bot','webapp_url':'https://example.test','webhook_secret':'test-placeholder-'*4}.items():
        monkeypatch.setattr(cfg,k,v)
    remote=AsyncMock(return_value={'username':'OtherBot'})
    monkeypatch.setattr('services.api.hosted.telegram',remote)
    with pytest.raises(RuntimeError,match='does not match'):
        await configure_telegram()
    assert remote.call_count==1
