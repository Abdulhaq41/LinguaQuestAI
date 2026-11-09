import uuid
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from ..models import User, Order, Payment, Plan, now
from ..config import settings
from .learning import emit

PERIOD = 2592000

async def telegram(method, **data):
    if not settings().bot_token: raise HTTPException(503, 'Telegram ещё не подключён')
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f'https://api.telegram.org/bot{settings().bot_token}/{method}', json=data)
        payload = response.json()
        if response.status_code != 200 or not payload.get('ok'): raise ValueError('Telegram request rejected')
        return payload['result']
    except (httpx.HTTPError, ValueError):
        # Never log response URLs containing the bot token.
        raise HTTPException(502, 'Telegram временно недоступен. Попробуйте позже')

def entitlement(db, uid):
    payment = db.scalar(select(Payment).where(Payment.user_id == uid, Payment.refunded.is_(False), Payment.grants_access.is_(True), Payment.expires_at > now()).order_by(Payment.expires_at.desc()))
    if not payment: return None
    order = db.get(Order, payment.order_id)
    return {'plan': order.plan_id, 'expires_at': payment.expires_at, 'auto_renew': not order.subscription_canceled, 'charge_id': payment.charge_id}

def require_paid(db, uid, ai=False):
    sub = entitlement(db, uid)
    if not sub: raise HTTPException(402, 'Для продолжения нужна подписка')
    if ai and sub['plan'] == 'START': raise HTTPException(403, 'AI-наставник доступен в PRO и ULTRA')
    return sub

async def checkout(db, user, plan_id):
    if not settings().commerce_enabled or not settings().support_contact:
        raise HTTPException(503, 'Продажи ещё не открыты. Владелец должен подключить бота, поддержку и утвердить условия')
    # Row lock makes two simultaneous checkout windows share one invoice.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    if entitlement(db, user.id): raise HTTPException(409, 'Смена тарифа доступна после завершения оплаченного периода. Сначала отключите продление')
    plan = db.get(Plan, plan_id)
    if not plan or not plan.enabled: raise HTTPException(404, 'Тариф недоступен')
    if plan_id != 'START':
        raise HTTPException(409, 'Продажа PRO/ULTRA закрыта: голосовой сервис ещё не готов. Доступен START')
    if not settings().production: raise HTTPException(503, 'Оплата разрешена только в production с HTTPS и настоящим ботом')
    pending = db.scalar(select(Order).where(Order.user_id == user.id, Order.status == 'pending', Order.expires_at > now()))
    if pending:
        if pending.plan_id != plan_id: raise HTTPException(409, 'Дождитесь окончания открытого счёта (15 минут)')
        return {'invoice_url': pending.invoice_url}
    order = Order(id=str(uuid.uuid4()), user_id=user.id, plan_id=plan.id, stars=plan.stars, expires_at=now()+900)
    db.add(order)
    db.flush()
    order.invoice_url = await telegram('createInvoiceLink', title=f'LinguaQuest {plan.id}', description='Доступ на 30 дней. Автопродление каждые 30 дней; отмена в профиле.', payload=order.id, provider_token='', currency='XTR', prices=[{'label': plan.id, 'amount': plan.stars}], subscription_period=PERIOD)
    emit(db, user.id, 'checkout_started', plan=plan.id)
    return {'invoice_url': order.invoice_url}

def validate_checkout(db, query):
    order = db.scalar(select(Order).where(Order.id == query['invoice_payload']).with_for_update())
    if not order or order.user_id != query['from']['id'] or query['currency'] != 'XTR' or query['total_amount'] != order.stars:
        return False
    if order.status == 'paid':
        return True  # Telegram renewal for this exact subscription.
    if order.status != 'pending' or order.expires_at <= now() or entitlement(db, order.user_id): return False
    if order.checkout_id and order.checkout_id != query['id']: return False
    order.checkout_id, order.checkout_at = query['id'], now()
    return True

def apply_payment(db, uid, payment):
    # Consistent lock order with account/subscription routes: user, then order.
    db.scalar(select(User).where(User.id == uid).with_for_update())
    order = db.scalar(select(Order).where(Order.id == payment['invoice_payload']).with_for_update())
    charge = payment['telegram_payment_charge_id']
    if not order or order.user_id != uid or payment['currency'] != 'XTR' or payment['total_amount'] != order.stars:
        raise HTTPException(400, 'Параметры платежа не совпадают со счётом')
    existing = db.get(Payment, charge)
    if existing:
        if existing.order_id != order.id: raise HTTPException(409, 'Конфликт платежа')
        return False
    expires = payment.get('subscription_expiration_date')
    if not isinstance(expires, int) or not payment.get('is_recurring'):
        raise HTTPException(400, 'Ожидался подтверждённый платёж подписки Telegram')
    if payment.get('is_first_recurring'):
        if order.initial_charge_id and order.initial_charge_id != charge: raise HTTPException(409,'Повторная первая оплата по одному счёту')
        order.initial_charge_id = charge
    active = entitlement(db,uid)
    overlaps = bool(active and db.get(Payment,active['charge_id']).order_id != order.id)
    db.add(Payment(charge_id=charge, order_id=order.id, user_id=uid, stars=order.stars, expires_at=expires, recurring=True,grants_access=not overlaps,refund_pending=overlaps))
    if overlaps:emit(db,uid,'payment_overlap_refund_pending',charge_id=charge)
    order.status = 'paid'
    emit(db, uid, 'purchase_successful', plan=order.plan_id, stars=order.stars)
    db.flush()
    from .referrals import reward
    if not overlaps:reward(db,uid,charge)
    return True
