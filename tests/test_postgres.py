"""Run only against a disposable local validation PostgreSQL instance."""
import os,uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import create_engine,select,func,text
from sqlalchemy.orm import sessionmaker
from services.api.models import User,Order,Payment,Attempt,Reward,now
from services.api.services.payments import apply_payment
from services.api.services.learning import complete,LESSONS

pytestmark=pytest.mark.skipif(not os.environ.get('TEST_POSTGRES_URL'),reason='Disposable PostgreSQL URL not configured')
@pytest.fixture
def pg():
    url=os.environ['TEST_POSTGRES_URL']
    if '127.0.0.1:55432/linguaquest' not in url:raise RuntimeError('Tests restricted to disposable localhost validation database')
    engine=create_engine(url,pool_size=8)
    yield sessionmaker(engine,expire_on_commit=False)
    engine.dispose()

def test_concurrent_payment_delivery_exactly_once(pg):
    uid=-uuid.uuid4().int%(2**50)
    oid=str(uuid.uuid4());charge=str(uuid.uuid4())
    with pg() as db:
        db.add(User(id=uid,name='Concurrency test'));db.flush()
        db.add(Order(id=oid,user_id=uid,plan_id='START',stars=89,expires_at=now()+900));db.commit()
    barrier=Barrier(6)
    data={'invoice_payload':oid,'telegram_payment_charge_id':charge,'currency':'XTR','total_amount':89,'is_recurring':True,'is_first_recurring':True,'subscription_expiration_date':now()+2592000}
    def process(_):
        with pg() as db:
            barrier.wait()
            result=apply_payment(db,uid,data);db.commit();return result
    with ThreadPoolExecutor(6) as pool:results=list(pool.map(process,range(6)))
    assert results.count(True)==1
    with pg() as db:assert db.scalar(select(func.count()).select_from(Payment).where(Payment.charge_id==charge))==1

def test_concurrent_lesson_completions_reward_once(pg):
    uid=-(uuid.uuid4().int%(2**50))-1
    ids=[str(uuid.uuid4()) for _ in range(4)]
    with pg() as db:
        db.add(User(id=uid,name='Reward test'));db.flush()
        for aid in ids:db.add(Attempt(id=aid,user_id=uid,lesson_id='first-hello',answers=[{'correct':True,'value':e['answers'][0]} for e in LESSONS['first-hello']['exercises']]))
        db.commit()
    barrier=Barrier(4)
    def process(aid):
        with pg() as db:
            barrier.wait()
            user=db.scalar(select(User).where(User.id==uid).with_for_update())
            result=complete(db,user,aid);db.commit();return result['xp_awarded']
    with ThreadPoolExecutor(4) as pool:results=list(pool.map(process,ids))
    assert sum(results)==50
    with pg() as db:
        assert db.get(User,uid).xp==50
        assert db.scalar(select(func.count()).select_from(Reward).where(Reward.user_id==uid,Reward.lesson_id=='first-hello'))==1


def test_concurrent_gift_requests_and_extension_apply_once(pg):
    from services.api.routes.admin_tools import create_grant,extend_grant,GrantCreate,Extend
    from services.api.models import AccessGrant,AdminAudit
    actor_id=uuid.uuid4().int%(2**50)
    target_id=actor_id+1
    with pg() as db:
        db.add_all([User(id=actor_id,name='Gift administrator'),User(id=target_id,name='Gift recipient')]);db.commit()
    request_id=uuid.uuid4()
    body=GrantCreate(request_id=request_id,reason='Concurrent gift test',user_id=target_id,plan='PRO',days=30)
    barrier=Barrier(6)
    def create(_):
        with pg() as db:
            actor=db.get(User,actor_id)
            barrier.wait()
            result=create_grant(body,admin=actor,db=db);db.commit();return result
    with ThreadPoolExecutor(6) as pool:results=list(pool.map(create,range(6)))
    assert all(result==results[0] for result in results)
    with pg() as db:
        assert db.scalar(select(func.count()).select_from(AccessGrant).where(AccessGrant.user_id==target_id))==1
        assert db.get(AdminAudit,str(request_id)) is not None
    gift=results[0]
    extension=Extend(request_id=uuid.uuid4(),reason='Concurrent extension test',days=7)
    barrier=Barrier(6)
    def extend(_):
        with pg() as db:
            actor=db.get(User,actor_id)
            barrier.wait()
            result=extend_grant(gift['id'],extension,admin=actor,db=db);db.commit();return result
    with ThreadPoolExecutor(6) as pool:results=list(pool.map(extend,range(6)))
    assert all(result['expires_at']==gift['expires_at']+7*86400 for result in results)


def test_administrators_can_grant_each_other_without_deadlock(pg):
    from services.api.routes.admin_tools import create_grant,GrantCreate
    actor_id=uuid.uuid4().int%(2**50)
    other_id=actor_id+1
    with pg() as db:
        db.add_all([User(id=actor_id,name='Administrator A'),User(id=other_id,name='Administrator B')]);db.commit()
    barrier=Barrier(2)
    def create(pair):
        actor_id,target_id=pair
        with pg() as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            actor=db.get(User,actor_id)
            barrier.wait()
            result=create_grant(GrantCreate(request_id=uuid.uuid4(),reason='Cross-admin concurrency test',user_id=target_id,days=7),admin=actor,db=db)
            db.commit();return result
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(create,[(actor_id,other_id),(other_id,actor_id)]))
    assert {r['user_id'] for r in results}=={actor_id,other_id}
