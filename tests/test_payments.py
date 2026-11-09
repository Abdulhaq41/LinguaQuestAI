import uuid
import pytest
from fastapi import HTTPException
from services.api.models import User,Order,Payment,now
from services.api.services.payments import apply_payment,validate_checkout,entitlement

@pytest.fixture
def order(db):
    db.add(User(id=42,name='Alex'));db.flush()
    o=Order(id=str(uuid.uuid4()),user_id=42,plan_id='START',stars=89,status='pending',expires_at=now()+900)
    db.add(o);db.commit()
    return o

def payment(order,charge='charge1',**changes):
    return {'invoice_payload':order.id,'telegram_payment_charge_id':charge,'currency':'XTR','total_amount':89,'is_recurring':True,'subscription_expiration_date':now()+2592000}|changes

def query(order,**changes):
    return {'id':'query1','invoice_payload':order.id,'from':{'id':42},'currency':'XTR','total_amount':89}|changes

def test_verified_payment_and_duplicate(db,order):
    assert apply_payment(db,42,payment(order))
    db.commit()
    assert not apply_payment(db,42,payment(order))
    assert entitlement(db,42)['plan']=='START'
    assert len(db.query(Payment).all())==1

@pytest.mark.parametrize('changes',[{'currency':'USD'},{'total_amount':1},{'is_recurring':False},{'subscription_expiration_date':None},{'invoice_payload':'fake'}])
def test_invalid_payment_never_grants(db,order,changes):
    with pytest.raises(HTTPException):apply_payment(db,42,payment(order,**changes))
    assert entitlement(db,42) is None

def test_wrong_payer(db,order):
    with pytest.raises(HTTPException):apply_payment(db,43,payment(order))

def test_two_checkout_windows(db,order):
    assert validate_checkout(db,query(order))
    assert validate_checkout(db,query(order))
    assert not validate_checkout(db,query(order,id='query2'))

def test_expired_checkout(db,order):
    order.expires_at=now()-1;db.flush()
    assert not validate_checkout(db,query(order))

def test_renewal_out_of_order(db,order):
    end=now()+2592000
    apply_payment(db,42,payment(order,'renewal',subscription_expiration_date=end+2592000))
    apply_payment(db,42,payment(order,'initial',subscription_expiration_date=end))
    db.commit()
    assert entitlement(db,42)['expires_at']==end+2592000

def test_refund_revokes_and_expiration(db,order):
    apply_payment(db,42,payment(order));db.commit()
    p=db.get(Payment,'charge1');p.refunded=True;db.flush()
    assert entitlement(db,42) is None
    p.refunded=False;p.expires_at=now()-1;db.flush()
    assert entitlement(db,42) is None

def test_checkout_disabled_without_real_configuration(member):
    r=member.post('/api/subscription/checkout',json={'plan':'START'})
    assert r.status_code==503
    assert member.get('/api/users/me').json()['subscription'] is None

def test_premium_sales_disabled(member,monkeypatch):
    from services.api.config import settings
    monkeypatch.setattr(settings(),'commerce_enabled',True)
    monkeypatch.setattr(settings(),'support_contact','support@example.com')
    assert member.post('/api/subscription/checkout',json={'plan':'PRO'}).status_code==409

def test_ai_gated(member):
    r=member.post('/api/ai/tutor',json={'request_id':str(uuid.uuid4()),'message':'Explain am'})
    assert r.status_code==402

def test_late_overlapping_payment_quarantined(db,order):
    apply_payment(db,42,payment(order,'first',is_first_recurring=True));db.commit()
    other=Order(id=str(uuid.uuid4()),user_id=42,plan_id='START',stars=89,status='pending',expires_at=now()+900)
    db.add(other);db.commit()
    apply_payment(db,42,payment(other,'late',is_first_recurring=True));db.commit()
    late=db.get(Payment,'late')
    assert late.refund_pending and not late.grants_access
    assert entitlement(db,42)['charge_id']=='first'
