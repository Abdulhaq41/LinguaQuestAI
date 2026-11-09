import uuid
from services.api.models import User,Order,Word,Referral,Payment,AIUsage,now
from services.api.services.payments import apply_payment
from services.api.services.referrals import register,revoke
from services.api.services.learning import LESSONS
from .test_learning import solve

def subscribe(member,db,plan='START'):
    uid=member.get('/api/users/me').json()['id']
    order=Order(id=str(uuid.uuid4()),user_id=uid,plan_id=plan,stars=89 if plan=='START' else 149,status='paid',expires_at=now()+900)
    db.add(order);db.flush()
    apply_payment(db,uid,{'invoice_payload':order.id,'telegram_payment_charge_id':str(uuid.uuid4()),'currency':'XTR','total_amount':order.stars,'is_recurring':True,'subscription_expiration_date':now()+2592000})
    db.commit()
    return uid

def test_assessment_does_not_claim_advanced_level(member):
    qs=member.get('/api/assessment').json()
    assert len(qs['questions'])==6 and all('answer' not in q for q in qs['questions'])
    result=member.post('/api/assessment',json={'answers':['Hello','is','London','went','No','will call']}).json()
    assert result['level']=='A2 practice'
    assert result['correct']==6
    assert member.get('/api/users/me').json()['settings']['assessment']==result

def test_words_and_srs_idempotency(member,db):
    uid=subscribe(member,db)
    attempt=solve(member)
    member.post(f'/api/attempts/{attempt["id"]}/complete')
    words=member.get('/api/vocabulary').json()
    assert len(words)==4
    review=member.post('/api/vocabulary/review/start').json()
    word=db.get(Word,db.get(__import__('services.api.models',fromlist=['Review']).Review,review['id']).word_id)
    route='/api/vocabulary/review/'+review['id']
    first=member.post(route,json={'answer':word.word})
    assert first.json()['correct']
    assert member.post(route,json={'answer':word.word}).json()==first.json()
    db.refresh(word)
    assert word.reviews==1 and word.interval_days==1
    assert member.post(route,json={'answer':'wrong'}).status_code==409

def test_daily_reward_once(member):
    assert member.post('/api/daily-quest/claim').status_code==409
    a=solve(member);member.post(f'/api/attempts/{a["id"]}/complete')
    before=member.get('/api/users/me').json()['coins']
    assert member.post('/api/daily-quest/claim').status_code==200
    member.post('/api/daily-quest/claim')
    assert member.get('/api/users/me').json()['coins']==before+5

def test_achievement_catalog_and_unique_rewards(member):
    a=solve(member);member.post(f'/api/attempts/{a["id"]}/complete')
    catalog=member.get('/api/achievements').json()
    assert len(catalog)==25
    assert any(a['earned_at'] for a in catalog)
    before=member.get('/api/users/me').json()['coins']
    member.get('/api/achievements');member.get('/api/achievements')
    assert member.get('/api/users/me').json()['coins']==before

def test_cosmetic_purchase_once_and_insufficient_balance(member,db):
    assert member.post('/api/shop/aqua-frame').status_code==409
    uid=member.get('/api/users/me').json()['id']
    user=db.get(User,uid);user.coins=100;db.commit()
    assert member.post('/api/shop/aqua-frame').json()['coins']==70
    assert member.post('/api/shop/aqua-frame').json()['coins']==70
    assert member.get('/api/users/me').json()['settings']['frame']=='aqua-frame'

def test_referral_reward_and_refund(db):
    inviter=User(id=100,name='Inviter',settings={'referral_code':'code'},coins=0)
    friend=User(id=101,name='Friend',settings={})
    db.add_all([inviter,friend]);db.flush()
    register(db,friend,'ref_code');db.flush()
    order=Order(id=str(uuid.uuid4()),user_id=101,plan_id='START',stars=89,expires_at=now()+900)
    db.add(order);db.commit()
    data={'invoice_payload':order.id,'telegram_payment_charge_id':'refcharge','currency':'XTR','total_amount':89,'is_recurring':True,'subscription_expiration_date':now()+2592000}
    apply_payment(db,101,data);db.commit()
    assert inviter.coins==100
    apply_payment(db,101,data);db.commit()
    assert inviter.coins==100
    revoke(db,'refcharge');db.commit()
    assert inviter.coins==0
    revoke(db,'refcharge');db.commit()
    assert inviter.coins==0

def test_lifequest_tier_and_narrative(member,db):
    uid=subscribe(member,db)
    assert member.post('/api/lessons/life-airport/start').status_code==403
    for p in db.query(Payment).filter_by(user_id=uid):db.get(Order,p.order_id).plan_id='PRO'
    db.commit()
    a=member.post('/api/lessons/life-airport/start').json()
    assert a['exercise']['type']=='dialogue'
    response=member.post(f'/api/attempts/{a["id"]}/answer',json={'index':0,'value':'I am here for work.'}).json()
    assert response['correct'] and 'Рабочая поездка' in response['explanation']

def test_account_delete_erases_learning_extensions(member,db):
    a=solve(member);member.post(f'/api/attempts/{a["id"]}/complete')
    assert member.delete('/api/users/me').status_code==200
    assert db.query(Word).count()==0

def test_ai_unconfigured_does_not_consume(member,db):
    subscribe(member,db,'PRO')
    r=member.post('/api/ai/tutor',json={'request_id':str(uuid.uuid4()),'message':'Explain am'})
    assert r.status_code==503
    assert db.query(AIUsage).count()==0
