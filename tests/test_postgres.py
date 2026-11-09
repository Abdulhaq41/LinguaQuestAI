"""Run only against a disposable local validation PostgreSQL instance."""
import os,uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import create_engine,select,func
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
