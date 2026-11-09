from sqlalchemy import select,func
from ..models import User,Referral,Payment
from .learning import emit

def register(db,user,code):
    if not code or not code.startswith('ref_'):return
    referrer=db.scalar(select(User).where(User.settings['referral_code'].as_string()==code[4:]))
    if not referrer or referrer.id==user.id or db.get(Referral,user.id):return
    db.add(Referral(invitee_id=user.id,referrer_id=referrer.id))
    emit(db,user.id,'referral_opened')

def reward(db,user_id,charge):
    referral=db.scalar(select(Referral).where(Referral.invitee_id==user_id).with_for_update())
    if not referral or referral.rewarded:return
    paid=db.scalar(select(func.count()).select_from(Payment).where(Payment.user_id==user_id,Payment.refunded.is_(False)))
    if paid!=1:return
    referrer=db.scalar(select(User).where(User.id==referral.referrer_id).with_for_update())
    if referrer.settings.get('deleted'):return
    referrer.coins+=100
    referral.rewarded=True
    referral.reward_charge_id=charge
    emit(db,referrer.id,'referral_converted',coins=100)

def revoke(db,charge):
    referral=db.scalar(select(Referral).where(Referral.reward_charge_id==charge).with_for_update())
    if referral and referral.rewarded and not referral.revoked:
        referrer=db.scalar(select(User).where(User.id==referral.referrer_id).with_for_update())
        referrer.coins=max(0,referrer.coins-100)
        referral.revoked=True
        emit(db,referrer.id,'referral_reward_revoked')
