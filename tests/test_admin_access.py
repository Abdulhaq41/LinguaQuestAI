import uuid
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select
from services.api.config import settings
from services.api.models import User,AccessGrant,AdminAudit,Payment,Order,AIUsage,now
from services.api.security import new_session
from services.api.services.payments import apply_payment,entitlement

@pytest.fixture
def owner(member,db,monkeypatch):
    uid=member.get('/api/users/me').json()['id']
    monkeypatch.setattr(settings(),'admin_telegram_ids',str(uid))
    friend=User(id=4455667788,name='Family member',settings={'onboarded':True,'telegram_username':'relative_test'})
    db.add(friend);db.commit()
    return member,db,uid,friend.id

def action(**fields):return {'request_id':str(uuid.uuid4()),'reason':'Проверка подарочного доступа',**fields}
def grant(client,uid,plan='START',days=30,**extra):
    return client.post('/api/admin/grants',json=action(user_id=uid,plan=plan,days=days,**extra))
def as_user(client,db,uid):
    previous=client.cookies.get('lq_session')
    token=new_session(db,uid);db.commit();client.cookies.clear();client.cookies.set('lq_session',token)
    return previous

def restore(client,token):client.cookies.clear();client.cookies.set('lq_session',token)

def paid(db,uid,plan='START'):
    o=Order(id=str(uuid.uuid4()),user_id=uid,plan_id=plan,stars=89,expires_at=now()+900)
    db.add(o);db.flush()
    data={'invoice_payload':o.id,'telegram_payment_charge_id':str(uuid.uuid4()),'currency':'XTR','total_amount':89,'is_recurring':True,'is_first_recurring':True,'subscription_expiration_date':now()+86400*90}
    apply_payment(db,uid,data);db.commit()
    return o,data

@pytest.mark.parametrize('path',['/api/admin/users','/api/admin/grants','/api/admin/audit','/api/admin/system','/api/admin/plans','/api/admin/export/users.csv','/api/admin/export/payments.csv'])
def test_admin_reads_reject_regular_users(member,path):assert member.get(path).status_code==403

def test_no_first_user_or_client_side_admin_promotion(member):
    member.patch('/api/users/me/settings',json={'is_admin':True,'admin':True,'subscription':'ULTRA'})
    assert not member.get('/api/users/me').json()['is_admin']
    assert member.post('/api/admin/grants',json=action(user_id=1,plan='ULTRA',days=365)).status_code==403


def test_gift_unlocks_learning_without_fake_payment(owner):
    c,db,actor,uid=owner
    r=grant(c,uid)
    assert r.status_code==200,r.text
    assert r.json()['status']=='active'
    assert db.query(Payment).count()==0
    assert db.query(AdminAudit).one().actor_id==actor
    as_user(c,db,uid)
    profile=c.get('/api/users/me').json()
    assert profile['subscription']['source']=='gift'
    assert profile['subscription']['plan']=='START'
    assert profile['paid_subscription'] is None
    assert c.post('/api/lessons/cafe/start').status_code==200
    assert c.post('/api/lessons/life-airport/start').status_code==403


def test_pro_gift_opens_realized_story_features(owner):
    c,db,actor,uid=owner
    grant(c,uid,'PRO')
    as_user(c,db,uid)
    assert c.post('/api/lessons/life-airport/start').status_code==200


def test_grant_request_idempotent_and_parameter_conflict(owner):
    c,db,actor,uid=owner
    body=action(user_id=uid,plan='START',days=30)
    first=c.post('/api/admin/grants',json=body)
    assert c.post('/api/admin/grants',json=body).json()==first.json()
    assert db.query(AccessGrant).count()==1 and db.query(AdminAudit).count()==1
    assert c.post('/api/admin/grants',json={**body,'days':60}).status_code==409


def test_extend_and_revoke_idempotent_with_audit(owner):
    c,db,actor,uid=owner
    g=grant(c,uid).json();body=action(days=7)
    route='/api/admin/grants/'+g['id']+'/extend'
    extended=c.post(route,json=body)
    assert extended.status_code==200,extended.text
    assert extended.json()['expires_at']==g['expires_at']+7*86400
    assert c.post(route,json=body).json()==extended.json()
    revoke=action();route='/api/admin/grants/'+g['id']+'/revoke'
    assert c.post(route,json=revoke).json()['status']=='revoked'
    c.post(route,json=revoke)
    assert db.query(AdminAudit).count()==3
    assert c.post('/api/admin/grants/'+g['id']+'/extend',json=action(days=1)).status_code==409
    as_user(c,db,uid)
    assert c.post('/api/lessons/cafe/start').status_code==402


def test_gift_never_hides_or_mutates_recurring_stars(owner):
    c,db,actor,uid=owner
    order,data=paid(db,uid)
    g=grant(c,uid,'PRO').json()
    as_user(c,db,uid)
    profile=c.get('/api/users/me').json()
    assert profile['subscription']['plan']=='PRO' and profile['subscription']['source']=='gift'
    assert profile['paid_subscription']['plan']=='START' and profile['paid_subscription']['auto_renew']
    assert profile['paid_subscription']['source']=='stars'
    # A real renewal during a higher-tier gift must not be quarantined as an overlap.
    renewal={**data,'telegram_payment_charge_id':str(uuid.uuid4()),'is_first_recurring':False,'subscription_expiration_date':now()+180*86400}
    apply_payment(db,uid,renewal);db.commit()
    assert not db.get(Payment,renewal['telegram_payment_charge_id']).refund_pending
    db.get(AccessGrant,g['id']).expires_at=now()-1;db.commit()
    sub=c.get('/api/users/me').json()['subscription']
    assert sub['source']=='stars' and sub['plan']=='START'
    assert db.get(Order,order.id).subscription_canceled is False


def test_revoking_gift_preserves_paid_period(owner):
    c,db,actor,uid=owner
    paid(db,uid)
    g=grant(c,uid,'ULTRA').json()
    c.post('/api/admin/grants/'+g['id']+'/revoke',json=action())
    assert entitlement(db,uid)['source']=='stars'
    assert db.query(Payment).one().refunded is False


def test_strongest_gift_and_expiration(owner):
    c,db,actor,uid=owner
    low=grant(c,uid,'START',90).json();high=grant(c,uid,'PRO',7).json()
    assert entitlement(db,uid)['plan']=='PRO'
    db.get(AccessGrant,high['id']).expires_at=now()-1;db.commit()
    assert entitlement(db,uid)['plan']=='START'
    db.get(AccessGrant,low['id']).expires_at=now()-1;db.commit()
    assert entitlement(db,uid) is None


@pytest.mark.parametrize('patch',[{'days':0},{'days':3651},{'plan':'OWNER'},{'reason':''},{'created_by':123},{'user_id':2**63}])
def test_grant_input_validation(owner,patch):
    c,db,actor,uid=owner
    body=action(user_id=uid,plan='START',days=30)
    assert c.post('/api/admin/grants',json={**body,**patch}).status_code==422
    assert db.query(AccessGrant).count()==0


def test_unknown_or_deleted_recipient_not_created(owner):
    c,db,actor,uid=owner
    assert grant(c,777).status_code==404
    db.get(User,uid).settings={'deleted':True};db.commit()
    assert grant(c,uid).status_code==409


def test_pause_learning_keeps_billing_and_personal_data_accessible(owner,monkeypatch):
    c,db,actor,uid=owner
    paid(db,uid)
    assert c.post(f'/api/admin/users/{uid}/learning-status',json=action(blocked=True)).status_code==200
    previous=as_user(c,db,uid)
    assert c.get('/api/users/me').status_code==200
    assert c.get('/api/users/me/export').status_code==200
    assert c.get('/api/subscription/history').status_code==200
    assert c.post('/api/lessons/first-hello/start').status_code==403
    assert c.post('/api/subscription/checkout',json={'plan':'START'}).status_code==403
    remote=AsyncMock(return_value=True);monkeypatch.setattr('services.api.routes.subscriptions.telegram',remote)
    assert c.post('/api/subscription/cancel').status_code==200
    restore(c,previous)
    assert c.post(f'/api/admin/users/{uid}/learning-status',json=action(blocked=False)).status_code==200
    as_user(c,db,uid)
    assert c.post('/api/lessons/cafe/start').status_code==200


def test_cannot_pause_an_administrator(owner):
    c,db,actor,uid=owner
    assert c.post(f'/api/admin/users/{actor}/learning-status',json=action(blocked=True)).status_code==409


def test_session_revoke_forces_new_login(owner):
    c,db,actor,uid=owner
    previous=as_user(c,db,uid);target_cookie=c.cookies.get('lq_session');restore(c,previous)
    result=c.post(f'/api/admin/users/{uid}/revoke-sessions',json=action())
    assert result.status_code==200 and result.json()['sessions_revoked']==1
    restore(c,target_cookie)
    assert c.get('/api/users/me').status_code==401


def test_coin_adjustment_once_and_cannot_overdraw(owner):
    c,db,actor,uid=owner
    body=action(delta=25);path=f'/api/admin/users/{uid}/coins'
    assert c.post(path,json=body).json()['coins']==25
    assert c.post(path,json=body).json()['coins']==25
    assert c.post(path,json=action(delta=-26)).status_code==409
    assert c.post(path,json=action(delta=-10)).json()['coins']==15
    assert db.get(User,uid).xp==0


def test_search_pagination_filters_and_admin_privacy(owner):
    c,db,actor,uid=owner
    grant(c,uid)
    data=c.get('/api/admin/users?q=@relative_test&status=gift').json()
    assert data['total']==1 and data['items'][0]['id']==uid
    assert c.get('/api/admin/users',params={'q':str(uid)}).json()['total']==1
    details=c.get(f'/api/admin/users/{uid}').json()
    assert details['progress']['completed_lessons']==0 and len(details['grants'])==1
    text=str(details)
    assert 'token_hash' not in text and 'ai_messages' not in text
    assert c.get('/api/admin/users?limit=0').status_code==422
    audit=c.get('/api/admin/audit?action=grant_created').json()
    assert audit['total']==1 and audit['items'][0]['target_id']==uid


def test_csv_defends_spreadsheet_formulas(owner):
    c,db,actor,uid=owner
    db.get(User,uid).name='=HYPERLINK("https://example.test")';db.commit()
    response=c.get('/api/admin/export/users.csv')
    assert response.status_code==200
    assert "'=HYPERLINK" in response.text
    assert db.query(AdminAudit).one().action=='csv_exported'


def test_dashboard_separates_gifts_from_revenue(owner):
    c,db,actor,uid=owner
    grant(c,uid)
    d=c.get('/api/admin/dashboard').json()
    assert d['active_gift_users']==1 and d['active_subscribers']==0
    assert d['gross_stars']==0 and d['refunded_stars']==0


def test_admin_can_pause_ai_without_consuming_usage(owner,monkeypatch):
    c,db,actor,uid=owner
    grant(c,uid,'PRO')
    assert c.post('/api/admin/system/ai-pause',json=action(paused=True)).status_code==200
    monkeypatch.setattr(settings(),'ai_enabled',True);monkeypatch.setattr(settings(),'ai_api_key','synthetic-test-placeholder')
    assert c.get('/api/config').json()['ai_connected'] is False
    as_user(c,db,uid)
    response=c.post('/api/ai/tutor',json={'request_id':str(uuid.uuid4()),'message':'Explain am'})
    assert response.status_code==503 and 'приостановлен' in response.json()['detail']
    assert db.query(AIUsage).count()==0


def test_self_deletion_revokes_gift_and_keeps_paid_cancel_protection(owner):
    c,db,actor,uid=owner
    g=grant(c,uid,'PRO').json()
    paid(db,uid)
    as_user(c,db,uid)
    assert c.delete('/api/users/me').status_code==409
    for order in db.query(Order).filter_by(user_id=uid):order.subscription_canceled=True
    db.commit()
    assert c.delete('/api/users/me').status_code==200
    assert db.get(AccessGrant,g['id']).revoked_at
    assert db.query(AdminAudit).count()==1


def test_no_real_keys_exposed_in_system(owner):
    c,db,actor,uid=owner
    text=c.get('/api/admin/system').text
    for key in ('bot_token','ai_api_key','database_url','webhook_secret'):
        assert key not in text
