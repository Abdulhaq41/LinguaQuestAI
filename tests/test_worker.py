from services.api.models import User,Notification
from services.worker.main import schedule

def test_worker_never_queues_dev_or_opted_out_users(db):
    db.add_all([User(id=-1,name='Dev',settings={'learning_notifications':True}),User(id=1000,name='Private',settings={'learning_notifications':False})]);db.commit()
    schedule(db);db.commit()
    assert db.query(Notification).count()==0
