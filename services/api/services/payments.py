import uuid
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from ..models import User, Order, Payment, Plan, AccessGrant, now
from ..config import settings
from .learning import emit

PERIOD = 2592000

class TelegramRequestError(HTTPException):
    """Safe metadata only: provider text and credential-bearing URLs stay private."""
    def __init__(self, reason, upstream_status=None, retry_after=None):
        super().__init__(502, 'Telegram временно недоступен. Попробуйте позже')
        self.reason = reason
        self.upstream_status = upstream_status
        self.retry_after = retry_after


async def telegram(method, **data):
    if not settings().bot_token: raise HTTPException(503, 'Telegram ещё не подключён')
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f'https://api.telegram.org/bot{settings().bot_token}/{method}', json=data)
    except httpx.InvalidURL:
        raise TelegramRequestError('invalid_bot_token_format') from None
    except httpx.TimeoutException:
        raise TelegramRequestError('request_timeout') from None
    except httpx.HTTPError:
        raise TelegramRequestError('network_error') from None
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    status = response.status_code
    if status == 200 and payload.get('ok') is True and 'result' in payload:
        return payload['result']
    description = payload.get('description', '')
    description = description.casefold() if isinstance(description, str) else ''
    reason = {401: 'invalid_bot_token', 403: 'telegram_forbidden',
              404: 'bot_api_not_found', 429: 'rate_limited'}.get(status)
    if status >= 500:
        reason = 'telegram_unavailable'
    if status == 400:
        if 'secret token' in description:
            reason = 'invalid_webhook_secret'
        elif 'bad webhook' in description:
            reason = 'webhook_rejected'
            if 'resolve' in description:
                reason = 'webhook_dns_error'
            elif 'ssl' in description or 'certificate' in description:
                reason = 'webhook_tls_error'
    parameters = payload.get('parameters', {})
    retry_after = parameters.get('retry_after') if isinstance(parameters, dict) else None
    if not isinstance(retry_after, int) or isinstance(retry_after, bool) or retry_after < 1:
        header = response.headers.get('Retry-After', '')
        retry_after = int(header) if header.isdigit() and int(header) > 0 else None
    if reason is None:
        reason = 'invalid_response' if not payload else 'request_rejected'
    raise TelegramRequestError(reason,
                               upstream_status=status, retry_after=retry_after) from None

def paid_entitlement(db, uid):
    payment = db.scalar(select(Payment).where(Payment.user_id == uid, Payment.refunded.is_(False), Payment.grants_access.is_(True), Payment.expires_at > now()).order_by(Payment.expires_at.desc()))
    if not payment: return None
    order = db.get(Order, payment.order_id)
    return {'plan': order.plan_id, 'expires_at': payment.expires_at, 'auto_renew': not order.subscription_canceled, 'charge_id': payment.charge_id, 'source': 'stars'}

PLAN_RANK = {'START':1, 'PRO':2, 'ULTRA':3}

def entitlement(db, uid):
    paid = paid_entitlement(db, uid)
    choices = [paid] if paid else []
    at = now()
    grants = db.scalars(select(AccessGrant).where(AccessGrant.user_id==uid, AccessGrant.revoked_at.is_(None), AccessGrant.starts_at<=at, AccessGrant.expires_at>at))
    for grant in grants:
        choices.append({'plan':grant.plan_id, 'expires_at':grant.expires_at, 'auto_renew':False,
                        'source':'gift', 'grant_id':grant.id})
    if not choices:return None
    return max(choices,key=lambda x:(PLAN_RANK[x['plan']], x['expires_at'], x['source']=='stars'))

def require_learning_enabled(user):
    if user and user.is_blocked:
        raise HTTPException(403,'Обучение приостановлено администратором. Профиль и управление оплатой остаются доступны')

def require_paid(db, uid, ai=False):
    require_learning_enabled(db.get(User, uid))
    sub = entitlement(db, uid)
    if not sub: raise HTTPException(402, 'Для продолжения нужна подписка')
    if ai and sub['plan'] == 'START': raise HTTPException(403, 'AI-наставник доступен в PRO и ULTRA')
    return sub

async def checkout(db, user, plan_id):
    require_learning_enabled(user)
    if not settings().commerce_enabled or not settings().support_contact:
        raise HTTPException(503, 'Продажи ещё не открыты. Владелец должен подключить бота, поддержку и утвердить условия')
    # Row lock makes two simultaneous checkout windows share one invoice.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    if entitlement(db, user.id): raise HTTPException(409, 'Подписка или подарок уже активны. Новая покупка доступна после окончания текущего доступа; продление Stars управляется в профиле')
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
    active = paid_entitlement(db,uid)
    overlaps = bool(active and db.get(Payment,active['charge_id']).order_id != order.id)
    db.add(Payment(charge_id=charge, order_id=order.id, user_id=uid, stars=order.stars, expires_at=expires, recurring=True,grants_access=not overlaps,refund_pending=overlaps))
    if overlaps:emit(db,uid,'payment_overlap_refund_pending',charge_id=charge)
    order.status = 'paid'
    emit(db, uid, 'purchase_successful', plan=order.plan_id, stars=order.stars)
    db.flush()
    from .referrals import reward
    if not overlaps:reward(db,uid,charge)
    return True
