import hashlib
import re
from unittest.mock import AsyncMock
import pytest
from services.api.config import Settings, settings
from services.api.hosted import configure_telegram

# Synthetic fixtures; never copy an actual deployment credential into a test.
BASE64_FIXTURE='synthetic+hosting/secret=fixture/for-tests-only=='

@pytest.mark.parametrize('raw', [BASE64_FIXTURE, 'x'*257, 'пример-секрета-для-теста-'*3])
def test_generated_webhook_secret_is_telegram_compatible(raw):
    cfg=Settings(_env_file=None,webhook_secret=raw)
    assert cfg.webhook_secret==hashlib.sha256(raw.encode()).hexdigest()
    assert 32<=len(cfg.webhook_secret)<=256
    assert re.fullmatch(r'[A-Za-z0-9_-]+',cfg.webhook_secret)

@pytest.mark.parametrize('raw', ['safe-test-placeholder_'*3,'a'*32,'b'*256])
def test_existing_compatible_webhook_secret_preserved(raw):
    assert Settings(_env_file=None,webhook_secret=raw).webhook_secret==raw

@pytest.mark.parametrize('raw', ['', 'short+secret/'])
def test_short_secret_not_expanded_to_bypass_startup_strength_check(raw):
    cfg=Settings(_env_file=None,webhook_secret=raw)
    assert cfg.webhook_secret==raw
    assert len(cfg.webhook_secret)<32

@pytest.mark.asyncio
async def test_registration_and_incoming_auth_use_same_derived_secret(client,monkeypatch):
    import services.api.main as api_module
    cfg=settings()
    normalized=Settings(_env_file=None,webhook_secret=BASE64_FIXTURE).webhook_secret
    for k,v in {'bot_token':'123456:synthetic-test-placeholder','bot_username':'Linguaquesttest_bot','webapp_url':'https://example.test','webhook_secret':normalized}.items():
        monkeypatch.setattr(cfg,k,v)
    remote=AsyncMock(side_effect=[{'username':'Linguaquesttest_bot'},True,True,True])
    monkeypatch.setattr('services.api.hosted.telegram',remote)
    await configure_telegram()
    sent=remote.call_args_list[1].kwargs['secret_token']
    assert sent==normalized
    class FakeDispatcher:
        feed_update=AsyncMock()
    class FakeBot:
        def __init__(self,*args,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
    dp=FakeDispatcher()
    monkeypatch.setattr(api_module,'_dp',dp)
    monkeypatch.setattr(api_module,'Bot',FakeBot)
    route='/api/telegram/webhook'
    assert client.post(route,json={'update_id':1},headers={'X-Telegram-Bot-Api-Secret-Token':sent}).status_code==200
    assert client.post(route,json={'update_id':2},headers={'X-Telegram-Bot-Api-Secret-Token':BASE64_FIXTURE}).status_code==403
    assert dp.feed_update.await_count==1
