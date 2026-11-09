import hashlib,hmac,json,time
from urllib.parse import urlencode
import pytest
from fastapi import HTTPException
from services.api.security import verify_init_data
from services.api.config import settings

def signed(token='123:token',**changes):
    fields={'auth_date':str(int(time.time())),'user':json.dumps({'id':42,'first_name':'Alex'})}|changes
    key=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(key,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
    return urlencode(fields)

def test_valid_telegram_signature():assert verify_init_data(signed(),'123:token')['id']==42

@pytest.mark.parametrize('data',[signed(auth_date='1'),signed(auth_date=str(int(time.time())+600)),signed()+'&user=bad',signed().replace('Alex','Evil'),'user=%7B%7D'])
def test_invalid_telegram_auth(data):
    with pytest.raises(HTTPException) as exc:verify_init_data(data,'123:token')
    assert exc.value.status_code==401

def test_authentication_required(client):
    assert client.get('/api/users/me').status_code==401
    assert client.post('/api/lessons/first-hello/start').status_code==401

def test_admin_denied(member):assert member.get('/api/admin/dashboard').status_code==403

def test_csrf(member):
    assert member.patch('/api/users/me/settings',json={},headers={'Origin':'https://evil.example'}).status_code==403

def test_forged_webhook(client):
    assert client.post('/api/telegram/webhook',json={}).status_code==403

def test_logout_revokes_session(member):
    cookie=member.cookies.get('lq_session')
    assert member.post('/api/auth/logout').status_code==200
    member.cookies.set('lq_session',cookie)
    assert member.get('/api/users/me').status_code==401

def test_dev_auth_disabled_in_production(client,monkeypatch):
    monkeypatch.setattr(settings(),'app_env','production')
    assert client.post('/api/auth/dev').status_code==404
