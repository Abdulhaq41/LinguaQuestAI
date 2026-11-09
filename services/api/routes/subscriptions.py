from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from ..db import get_db
from ..models import User, Plan, Payment, Order
from ..security import current_user
from ..services.payments import checkout, entitlement, telegram
from ..services.learning import emit
router=APIRouter(prefix='/subscription', tags=['Subscriptions'])

@router.get('/plans')
def plans(db=Depends(get_db)):
    return [{'id':p.id,'stars':p.stars,'days':30,'available':p.enabled and p.id=='START','features': {'START':['Уроки A1 и A2','Прогресс, XP и достижения','Без AI-разговоров'], 'PRO':['Всё из START','AI-наставник','150 минут голоса — в разработке'], 'ULTRA':['Всё из PRO','500 минут голоса — в разработке','Расширенные сценарии — в разработке']}[p.id]} for p in db.scalars(select(Plan).order_by(Plan.stars))]

class Checkout(BaseModel):
    plan:Literal['START','PRO','ULTRA']

@router.post('/checkout')
async def create(body:Checkout,user:User=Depends(current_user),db=Depends(get_db)):
    return await checkout(db,user,body.plan)

@router.get('/history')
def history(user:User=Depends(current_user),db=Depends(get_db)):
    return [{'charge_id':p.charge_id,'stars':p.stars,'expires_at':p.expires_at,'created_at':p.created_at,'refunded':p.refunded} for p in db.scalars(select(Payment).where(Payment.user_id==user.id).order_by(Payment.created_at.desc()))]

@router.post('/cancel')
async def cancel(user:User=Depends(current_user),db=Depends(get_db)):
    db.scalar(select(User).where(User.id==user.id).with_for_update())
    orders=list(db.scalars(select(Order).where(Order.user_id==user.id,Order.status=='paid',Order.subscription_canceled.is_(False)).with_for_update()))
    for order in orders:
        if not order.initial_charge_id:raise HTTPException(409,'Ожидаем синхронизацию первого платежа. Обратитесь в поддержку')
        await telegram('editUserStarSubscription',user_id=user.id,telegram_payment_charge_id=order.initial_charge_id,is_canceled=True)
        order.subscription_canceled=True
        for payment in db.scalars(select(Payment).where(Payment.order_id==order.id)):payment.canceled=True
        # Persist each confirmed cancellation, including when a later order needs manual reconciliation.
        db.commit()
    if orders:emit(db,user.id,'subscription_canceled')
    return {'ok':True,'subscription':entitlement(db,user.id)}
