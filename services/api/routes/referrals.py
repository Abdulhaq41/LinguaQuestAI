from fastapi import APIRouter,Depends
from sqlalchemy import select
from ..db import get_db
from ..models import Referral
from ..security import current_user
from ..config import settings
router=APIRouter(prefix='/referrals',tags=['Referrals'])
@router.get('/me')
def stats(user=Depends(current_user),db=Depends(get_db)):
    code=user.settings.get('referral_code')
    username=settings().bot_username
    rows=list(db.scalars(select(Referral).where(Referral.referrer_id==user.id)))
    return {'link':f'https://t.me/{username}?startapp=ref_{code}' if username and code else None,'registered':len(rows),'converted':sum(r.rewarded and not r.revoked for r in rows),'coins_awarded':sum(100 for r in rows if r.rewarded and not r.revoked),'rules':'100 косметических монет за первую подтверждённую оплату друга. За открытие ссылки награды нет. При возврате бонус отзывается.'}
