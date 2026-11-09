"""One outbox worker. Telegram delivery is at least once, never financial authorization."""
import asyncio,uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select,delete
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.models import User,Session,Notification,Attempt,Payment,Order,now
from services.api.services.payments import telegram

def enqueue(db,uid,key,text):
    if not db.scalar(select(Notification.id).where(Notification.user_id==uid,Notification.key==key)):
        db.add(Notification(id=str(uuid.uuid4()),user_id=uid,key=key,text=text))

def schedule(db):
    for user in db.scalars(select(User)):
        if user.id<=0 or user.settings.get('deleted'):continue
        local=datetime.now(ZoneInfo(user.settings.get('timezone','Asia/Tashkent')))
        if user.settings.get('learning_notifications') and local.hour==18:
            start=int(local.replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
            active=db.scalar(select(Attempt.id).where(Attempt.user_id==user.id,Attempt.completed_at>=start,Attempt.score>=70).limit(1))
            if not active:enqueue(db,user.id,'lesson:'+local.date().isoformat(),'✨ Lexi ждёт! Если сегодня есть пять минут, продолжим английское приключение. Напоминания можно отключить в профиле.')
        payment=db.scalar(select(Payment).where(Payment.user_id==user.id,Payment.refunded.is_(False),Payment.expires_at>now()).order_by(Payment.expires_at.desc()))
        if payment and 0<payment.expires_at-now()<86400:
            enqueue(db,user.id,'expiry:'+payment.charge_id,'💎 До завершения текущего периода LinguaQuest осталось меньше суток. Проверьте срок действия и автопродление в профиле. /paysupport — помощь с оплатой.')
    db.execute(delete(Session).where(Session.expires_at<now()))

async def tick():
    with SessionLocal() as db:
        pending=list(db.scalars(select(Payment).where(Payment.refund_pending.is_(True),Payment.refunded.is_(False)).with_for_update(skip_locked=True)))
        for payment in pending:
            try:
                order=db.get(Order,payment.order_id)
                if not order.subscription_canceled and order.initial_charge_id:
                    await telegram('editUserStarSubscription',user_id=payment.user_id,telegram_payment_charge_id=order.initial_charge_id,is_canceled=True)
                    order.subscription_canceled=True
                await telegram('refundStarPayment',user_id=payment.user_id,telegram_payment_charge_id=payment.charge_id)
                payment.refunded=True;payment.refund_pending=False;payment.grants_access=False
            except Exception:print('Automatic overlap refund pending; requires retry or support',flush=True)
        db.commit()
    with SessionLocal() as db:
        schedule(db);db.commit()
    for _ in range(50):
        with SessionLocal() as db:
            item=db.scalar(select(Notification).where(Notification.sent_at.is_(None),Notification.created_at>now()-86400).order_by(Notification.created_at).with_for_update(skip_locked=True).limit(1))
            if not item:break
            user=db.get(User,item.user_id)
            if not user or user.settings.get('deleted') or (item.key.startswith('lesson:') and not user.settings.get('learning_notifications')):
                item.sent_at=now();db.commit();continue
            try:
                await telegram('sendMessage',chat_id=item.user_id,text=item.text)
                item.sent_at=now();db.commit()
            except Exception:
                # Avoid printing exceptions containing provider request URLs or user data.
                db.rollback()
                print('Notification delivery failed; will retry later',flush=True)
                break

async def main():
    if not settings().bot_token:raise RuntimeError('BOT_TOKEN required for notification worker')
    while True:
        await tick()
        await asyncio.sleep(60)
if __name__=='__main__':asyncio.run(main())
