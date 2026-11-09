import uuid
from unittest.mock import AsyncMock
from services.api.models import Order,Payment,User,AIUsage,now
from services.api.config import settings
from services.api.services.payments import apply_payment
from .test_game import subscribe
from .test_security import signed

def test_real_auth_route_uses_signed_identity(client,monkeypatch):
    monkeypatch.setattr(settings(),'bot_token','123:token')
    assert client.post('/api/auth/telegram',json={'init_data':signed()}).status_code==200
    assert client.get('/api/users/me').json()['id']==42

def test_admin_price_and_audit(member,db,monkeypatch):
    uid=member.get('/api/users/me').json()['id']
    monkeypatch.setattr(settings(),'admin_telegram_ids',str(uid))
    assert member.patch('/api/admin/plans/START',json={'stars':99}).status_code==200
    assert member.get('/api/subscription/plans').json()[0]['stars']==99
    data=member.get('/api/admin/dashboard').json()
    assert any(e['event']=='admin_price_changed' for e in data['events'])

def test_invoice_created_once_and_access_only_after_payment(member,db,monkeypatch):
    from services.api.services import payments
    cfg=settings()
    monkeypatch.setattr(cfg,'commerce_enabled',True);monkeypatch.setattr(cfg,'support_contact','test-support')
    monkeypatch.setattr(cfg,'app_env','production')
    telegram=AsyncMock(return_value='https://t.me/$synthetic-test-invoice')
    monkeypatch.setattr(payments,'telegram',telegram)
    first=member.post('/api/subscription/checkout',json={'plan':'START'})
    assert first.status_code==200,first.text
    assert member.post('/api/subscription/checkout',json={'plan':'START'}).json()==first.json()
    assert telegram.call_count==1
    assert member.post('/api/lessons/cafe/start').status_code==402
    order=db.query(Order).one()
    apply_payment(db,order.user_id,{'invoice_payload':order.id,'telegram_payment_charge_id':'verified-test-event','currency':'XTR','total_amount':89,'is_recurring':True,'is_first_recurring':True,'subscription_expiration_date':now()+2592000})
    db.commit()
    assert member.post('/api/lessons/cafe/start').status_code==200
    assert member.post('/api/subscription/checkout',json={'plan':'START'}).status_code==409

def test_cancel_and_refund_through_mocked_telegram(member,db,monkeypatch):
    uid=subscribe(member,db)
    payment=db.query(Payment).filter_by(user_id=uid).one()
    order=db.get(Order,payment.order_id);order.initial_charge_id=payment.charge_id;db.commit()
    remote=AsyncMock(return_value=True)
    monkeypatch.setattr('services.api.routes.subscriptions.telegram',remote)
    assert member.post('/api/subscription/cancel').status_code==200
    assert not member.get('/api/users/me').json()['subscription']['auto_renew']
    member.post('/api/subscription/cancel');assert remote.call_count==1
    monkeypatch.setattr(settings(),'admin_telegram_ids',str(uid))
    monkeypatch.setattr('services.api.routes.admin.telegram',remote)
    assert member.post('/api/admin/refund',json={'charge_id':payment.charge_id}).status_code==200
    assert member.get('/api/users/me').json()['subscription'] is None

def test_ai_real_adapter_mocked_transport_and_cache(member,db,monkeypatch):
    subscribe(member,db,'PRO')
    member.patch('/api/users/me/settings',json={'ai_consent':True})
    monkeypatch.setattr(settings(),'ai_enabled',True)
    monkeypatch.setattr(settings(),'ai_api_key','synthetic-test-placeholder')
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'results':[{'flagged':False}],'choices':[{'message':{'content':'Use I am, she is, and you are.'}}],'usage':{'prompt_tokens':20,'completion_tokens':15}}
    client=AsyncMock();client.post.return_value=Response()
    cm=AsyncMock();cm.__aenter__.return_value=client
    monkeypatch.setattr('services.api.routes.ai.httpx.AsyncClient',lambda **kw:cm)
    data={'request_id':str(uuid.uuid4()),'message':'Explain am'}
    answer=member.post('/api/ai/tutor',json=data)
    assert answer.status_code==200,answer.text
    assert answer.json()['answer'].startswith('Use I am')
    cached=member.post('/api/ai/tutor',json=data)
    assert cached.json()['cached'] and client.post.call_count==3
    assert db.query(AIUsage).one().input_tokens==20

def test_provider_failure_not_in_user_quota(member,db,monkeypatch):
    import httpx
    subscribe(member,db,'PRO');member.patch('/api/users/me/settings',json={'ai_consent':True})
    monkeypatch.setattr(settings(),'ai_enabled',True);monkeypatch.setattr(settings(),'ai_api_key','synthetic-test-placeholder')
    client=AsyncMock();client.post.side_effect=httpx.ReadTimeout('test timeout')
    cm=AsyncMock();cm.__aenter__.return_value=client
    monkeypatch.setattr('services.api.routes.ai.httpx.AsyncClient',lambda **kw:cm)
    r=member.post('/api/ai/tutor',json={'request_id':str(uuid.uuid4()),'message':'Explain am'})
    assert r.status_code==502
    assert db.query(AIUsage).one().status=='failed'

def test_content_versions_preserve_active_attempt(member,db,monkeypatch):
    from copy import deepcopy
    from services.api.services.learning import LESSONS
    uid=member.get('/api/users/me').json()['id']
    monkeypatch.setattr(settings(),'admin_telegram_ids',str(uid))
    attempt=member.post('/api/lessons/first-hello/start').json()
    content=deepcopy(LESSONS['first-hello'])
    content['exercises'][0]['answers']=['Goodbye']
    r=member.put('/api/admin/lessons/first-hello',json={'expected_version':0,'content':content})
    assert r.status_code==200,r.text
    assert r.json()['version']==1
    assert member.put('/api/admin/lessons/first-hello',json={'expected_version':0,'content':content}).status_code==409
    answer=member.post(f'/api/attempts/{attempt["id"]}/answer',json={'index':0,'value':'Hello'})
    assert answer.json()['correct']
    versions=member.get('/api/admin/lessons').json()
    assert next(v for v in versions if v['id']=='first-hello')['version']==1

def test_can_cancel_after_access_refunded_or_expired(member,db,monkeypatch):
    uid=subscribe(member,db)
    payment=db.query(Payment).filter_by(user_id=uid).one()
    order=db.get(Order,payment.order_id)
    order.initial_charge_id=payment.charge_id
    payment.refunded=True;payment.expires_at=now()-10;db.commit()
    remote=AsyncMock(return_value=True)
    monkeypatch.setattr('services.api.routes.subscriptions.telegram',remote)
    assert member.get('/api/users/me').json()['subscription'] is None
    assert member.post('/api/subscription/cancel').status_code==200
    assert remote.call_count==1
    db.refresh(order);assert order.subscription_canceled

def test_ai_quota_enforced_before_provider(member,db,monkeypatch):
    from datetime import datetime,timezone
    uid=subscribe(member,db,'PRO')
    member.patch('/api/users/me/settings',json={'ai_consent':True})
    monkeypatch.setattr(settings(),'ai_enabled',True);monkeypatch.setattr(settings(),'ai_api_key','synthetic-test-placeholder')
    for _ in range(30):db.add(AIUsage(id=str(uuid.uuid4()),user_id=uid,day=datetime.now(timezone.utc).date().isoformat(),status='success',input_tokens=1,output_tokens=1))
    db.commit()
    r=member.post('/api/ai/tutor',json={'request_id':str(uuid.uuid4()),'message':'Explain am'})
    assert r.status_code==429

def test_ai_moderation_blocks_without_generation(member,db,monkeypatch):
    subscribe(member,db,'PRO');member.patch('/api/users/me/settings',json={'ai_consent':True})
    monkeypatch.setattr(settings(),'ai_enabled',True);monkeypatch.setattr(settings(),'ai_api_key','synthetic-test-placeholder')
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'results':[{'flagged':True}]}
    client=AsyncMock();client.post.return_value=Response()
    cm=AsyncMock();cm.__aenter__.return_value=client
    monkeypatch.setattr('services.api.routes.ai.httpx.AsyncClient',lambda **kw:cm)
    request={'request_id':str(uuid.uuid4()),'message':'synthetic moderation test'}
    assert member.post('/api/ai/tutor',json=request).status_code==422
    assert client.post.call_count==1
    assert db.query(AIUsage).one().status=='blocked'
    assert member.post('/api/ai/tutor',json=request).status_code==409
