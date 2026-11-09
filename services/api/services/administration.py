"""Audited, transactional administration. No operation fabricates payment records."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..models import User, AdminAudit, AccessGrant, now

MAX_GIFT_DAYS=3650

def target_user(db, uid):
    # NO KEY UPDATE serializes balances/grants while allowing FK references to administrators.
    user=db.scalar(select(User).where(User.id==uid).with_for_update(key_share=True).execution_options(populate_existing=True))
    if not user:raise HTTPException(404,'Пользователь не найден. Попросите его сначала открыть Mini App')
    return user

def replay(db, request_id, actor, action, target, inputs):
    record=db.get(AdminAudit,str(request_id))
    if not record:return None
    if (record.actor_id,record.action,record.target_id,record.details.get('input'))!=(actor.id,action,target,inputs):
        raise HTTPException(409,'Идентификатор операции уже используется для другого действия')
    return record.details['result']

def audit(db, actor, action, target=None, inputs=None, result=None, request_id=None):
    record=AdminAudit(id=str(request_id or uuid.uuid4()),actor_id=actor.id,target_id=target,action=action,
                      details={'input':inputs or {},'result':result or {}})
    db.add(record)
    try:db.flush()
    except IntegrityError:
        raise HTTPException(409,'Операция уже записана. Обновите данные перед повтором') from None
    return record

def grant_data(grant):
    at=now()
    status='revoked' if grant.revoked_at else 'expired' if grant.expires_at<=at else 'scheduled' if grant.starts_at>at else 'active'
    return {'id':grant.id,'user_id':grant.user_id,'plan':grant.plan_id,'source':'gift','created_by':grant.created_by,
            'reason':grant.reason,'starts_at':grant.starts_at,'expires_at':grant.expires_at,'created_at':grant.created_at,
            'revoked_at':grant.revoked_at,'revoke_reason':grant.revoke_reason,'status':status}
