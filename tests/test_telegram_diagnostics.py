from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from services.api.config import settings
from services.api.services.payments import telegram, TelegramRequestError
from services.api import hosted

MARKER='SYNTHETIC_PRIVATE_DATA_DO_NOT_EXPOSE'

@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setattr(settings(),'bot_token','synthetic-test-placeholder')
    remote=AsyncMock()
    cm=AsyncMock()
    cm.__aenter__.return_value=remote
    monkeypatch.setattr('services.api.services.payments.httpx.AsyncClient',lambda **kw:cm)
    return remote

@pytest.mark.asyncio
async def test_telegram_success(transport):
    transport.post.return_value=httpx.Response(200,json={'ok':True,'result':{'username':'TestBot'}})
    assert await telegram('getMe')=={'username':'TestBot'}

@pytest.mark.asyncio
@pytest.mark.parametrize('status,payload,reason',[
    (401,{'ok':False,'description':MARKER},'invalid_bot_token'),
    (403,{'ok':False,'description':MARKER},'telegram_forbidden'),
    (404,{'ok':False,'description':MARKER},'bot_api_not_found'),
    (400,{'ok':False,'description':'Bad Request: secret token contains invalid characters '+MARKER},'invalid_webhook_secret'),
    (400,{'ok':False,'description':'Bad Request: bad webhook: Failed to resolve host '+MARKER},'webhook_dns_error'),
    (400,{'ok':False,'description':'Bad Request: bad webhook: SSL certificate error '+MARKER},'webhook_tls_error'),
    (400,{'ok':False,'description':'Bad Request: bad webhook: '+MARKER},'webhook_rejected'),
    (400,{'ok':False,'description':MARKER},'request_rejected'),
    (429,{'ok':False,'description':MARKER,'parameters':{'retry_after':12}},'rate_limited'),
    (503,{'ok':False,'description':MARKER},'telegram_unavailable'),
    (200,[], 'invalid_response'),
])
async def test_provider_failure_exposes_only_safe_codes(transport,status,payload,reason):
    transport.post.return_value=httpx.Response(status,json=payload)
    with pytest.raises(TelegramRequestError) as caught:
        await telegram('getMe')
    err=caught.value
    assert err.reason==reason
    assert err.upstream_status==status
    assert err.status_code==502
    assert MARKER not in str(err) and MARKER not in err.detail
    if status==429:assert err.retry_after==12

@pytest.mark.asyncio
@pytest.mark.parametrize('exc,reason',[
    (httpx.InvalidURL(MARKER),'invalid_bot_token_format'),
    (httpx.ReadTimeout(MARKER),'request_timeout'),
    (httpx.ConnectError(MARKER),'network_error'),
])
async def test_network_exception_text_never_exposed(transport,exc,reason):
    transport.post.side_effect=exc
    with pytest.raises(TelegramRequestError) as caught:
        await telegram('getMe')
    assert caught.value.reason==reason
    assert MARKER not in str(caught.value)

@pytest.mark.asyncio
async def test_plain_proxy_throttle_honors_retry_after(transport):
    transport.post.return_value=httpx.Response(429,text=MARKER,headers={'Retry-After':'17'})
    with pytest.raises(TelegramRequestError) as caught:
        await telegram('getMe')
    assert caught.value.reason=='rate_limited' and caught.value.retry_after==17

@pytest.fixture
def readiness(monkeypatch):
    probe=AsyncMock()
    probe.get.return_value=SimpleNamespace(is_success=True)
    cm=AsyncMock();cm.__aenter__.return_value=probe
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:cm)
    pause=AsyncMock()
    monkeypatch.setattr(hosted.asyncio,'sleep',pause)
    return pause

@pytest.mark.asyncio
async def test_invalid_token_stops_without_repeated_requests(readiness,monkeypatch,caplog):
    async def configure():
        hosted.DEPLOYMENT['step']='getMe'
        raise TelegramRequestError('invalid_bot_token',upstream_status=401)
    call=AsyncMock(side_effect=configure)
    monkeypatch.setattr(hosted,'configure_telegram',call)
    await hosted.configure_after_start()
    assert hosted.DEPLOYMENT=={'telegram':'failed','step':'getMe','error':'invalid_bot_token','attempt':1,'http_status':401}
    assert call.await_count==1 and readiness.await_count==0
    assert MARKER not in caplog.text

@pytest.mark.asyncio
async def test_temporary_failure_retried_then_ready(readiness,monkeypatch):
    n=0
    async def configure():
        nonlocal n
        n+=1
        hosted.DEPLOYMENT['step']='setWebhook'
        if n==1:raise TelegramRequestError('rate_limited',429,retry_after=11)
        hosted.set_deployment('ready')
    monkeypatch.setattr(hosted,'configure_telegram',configure)
    await hosted.configure_after_start()
    assert n==2 and hosted.DEPLOYMENT=={'telegram':'ready'}
    readiness.assert_awaited_once_with(11)

@pytest.mark.asyncio
async def test_all_transient_failures_report_last_step(readiness,monkeypatch):
    async def configure():
        hosted.DEPLOYMENT['step']='setWebhook'
        raise TelegramRequestError('request_timeout')
    monkeypatch.setattr(hosted,'configure_telegram',configure)
    await hosted.configure_after_start()
    assert hosted.DEPLOYMENT=={'telegram':'failed','step':'setWebhook','error':'request_timeout','attempt':5}
    assert readiness.await_count==4

@pytest.mark.asyncio
async def test_unexpected_exception_never_leaks_to_status_or_logs(readiness,monkeypatch,caplog):
    monkeypatch.setattr(hosted,'configure_telegram',AsyncMock(side_effect=RuntimeError(MARKER)))
    await hosted.configure_after_start()
    assert hosted.DEPLOYMENT['error']=='internal_setup_error'
    assert MARKER not in json.dumps(hosted.DEPLOYMENT) and MARKER not in caplog.text

@pytest.mark.asyncio
async def test_wrong_username_explained_without_retry(readiness,monkeypatch):
    failure=hosted.TelegramSetupError('bot_username_mismatch','BOT_USERNAME does not match')
    monkeypatch.setattr(hosted,'configure_telegram',AsyncMock(side_effect=failure))
    await hosted.configure_after_start()
    assert hosted.DEPLOYMENT['telegram']=='failed'
    assert hosted.DEPLOYMENT['error']=='bot_username_mismatch'
    assert readiness.await_count==0


def test_public_status_contains_only_safe_metadata(tmp_path,monkeypatch):
    (tmp_path/'index.html').write_text('test')
    monkeypatch.setenv('AUTO_CONFIGURE_BOT','false')
    monkeypatch.setenv('RENDER_GIT_COMMIT','a'*40)
    with TestClient(hosted.attach_frontend(FastAPI(),tmp_path)) as client:
        hosted.set_deployment('failed',step='getMe',error='invalid_bot_token',http_status=401)
        data=client.get('/api/deployment/status').json()
        assert data=={'telegram':'failed','step':'getMe','error':'invalid_bot_token','http_status':401,'revision':'a'*7}
