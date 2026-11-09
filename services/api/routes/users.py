from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, delete
from ..db import get_db
from ..models import User, Attempt, Reward, Payment, Order, Event, Session, AIMessage, AIUsage, now
from ..security import current_user
from ..services.payments import entitlement
from ..services.learning import emit

router = APIRouter(tags=['Account'])
class Preferences(BaseModel):
    language: Literal['ru', 'uz', 'en'] = 'ru'
    goal: Literal['travel', 'work', 'study', 'conversation'] = 'travel'
    minutes: Literal[5,10,15,20] = 10
    timezone: str = Field(default='Asia/Tashkent', max_length=80)
    theme: Literal['dark','light'] = 'dark'
    public_profile: bool = False
    learning_notifications: bool = False
    marketing_notifications: bool = False
    ai_consent: bool = False
    sound: bool = False
    onboarded: bool = True
    @field_validator('timezone')
    @classmethod
    def tz(cls, value):
        try: ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError): raise ValueError('Unknown timezone')
        return value

def progress(db, user):
    attempts = list(db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.completed_at.is_not(None)).order_by(Attempt.completed_at.desc())))
    tz = ZoneInfo(user.settings.get('timezone', 'Asia/Tashkent'))
    dates = {datetime.fromtimestamp(a.completed_at, tz).date() for a in attempts if a.score >= 70}
    current = datetime.now(tz).date()
    if current not in dates: current -= timedelta(days=1)
    streak = 0
    while current in dates:
        streak += 1
        current -= timedelta(days=1)
    today = datetime.now(tz).date()
    return {'completed_lessons': len({a.lesson_id for a in attempts if a.score >= 70}), 'streak': streak, 'today_xp': sum(r.xp for r in db.scalars(select(Reward).where(Reward.user_id == user.id)) if datetime.fromtimestamp(r.created_at,tz).date() == today), 'history': [{'id': a.id, 'lesson_id': a.lesson_id, 'score': a.score, 'completed_at': a.completed_at, 'seconds': max(0,a.completed_at-a.started_at)} for a in attempts[:50]], 'achievements': [{'id':'first-step', 'title':'First Step', 'description':'Первый успешно завершённый урок'}] if dates else []}

@router.get('/users/me')
def me(user: User=Depends(current_user), db=Depends(get_db)):
    return {'id':user.id, 'name':user.name, 'xp':user.xp, 'coins':user.coins, 'level':1+user.xp//200, 'settings':user.settings, 'subscription':entitlement(db,user.id), 'progress':progress(db,user), 'route': {'level':'A1', 'note':'Стартовый маршрут, без сертифицированной оценки CEFR', 'focus':{'travel':'Знакомство → кафе → путешествие', 'work':'Знакомство → рабочий день → планы', 'study':'Знакомство → распорядок → прошлое', 'conversation':'Знакомство → кафе → диалоги'}.get(user.settings.get('goal'),'Знакомство → кафе')}}

@router.patch('/users/me/settings')
def update(body:Preferences, user:User=Depends(current_user), db=Depends(get_db)):
    if body.marketing_notifications:
        raise HTTPException(409, 'Маркетинговые рассылки пока недоступны')
    first = not user.settings.get('onboarded')
    user.settings = {**user.settings, **body.model_dump()}
    if first: emit(db,user.id,'onboarding_completed')
    return {'settings':user.settings}

@router.get('/leaderboard')
def leaderboard(user:User=Depends(current_user), db=Depends(get_db)):
    since=now()-7*86400
    rows=db.execute(select(User.id,User.name,func.sum(Reward.xp).label('xp')).join(Reward,Reward.user_id==User.id).where(Reward.created_at>=since).group_by(User.id,User.name)).all()
    visible=[]
    for uid,name,xp in rows:
        member=db.get(User,uid)
        if member.settings.get('public_profile'):
            visible.append({'name':name,'xp':xp,'me':uid==user.id})
    visible.sort(key=lambda x:-x['xp'])
    for row in visible: row['rank']=1+sum(other['xp']>row['xp'] for other in visible)
    return visible[:100]

@router.get('/users/me/export')
def export(user:User=Depends(current_user),db=Depends(get_db)):
    return {'profile':me(user,db), 'payments':[{'charge_id':p.charge_id,'stars':p.stars,'created_at':p.created_at,'refunded':p.refunded} for p in db.scalars(select(Payment).where(Payment.user_id==user.id))], 'ai_messages':[{'question':m.question,'answer':m.answer,'created_at':m.created_at} for m in db.scalars(select(AIMessage).where(AIMessage.user_id==user.id))]}

@router.delete('/users/me')
def erase(user:User=Depends(current_user), db=Depends(get_db)):
    sub=entitlement(db,user.id)
    if sub and sub['auto_renew']: raise HTTPException(409,'Сначала отключите автопродление в профиле')
    for model in (Session, Attempt, Reward, AIMessage, AIUsage):
        db.execute(delete(model).where(model.user_id==user.id))
    db.execute(delete(Event).where(Event.user_id==user.id))
    from ..models import Assessment, Word, Review, Achievement, Cosmetic, StoryProgress, Notification
    for model in (Assessment, Review, Word, Achievement, Cosmetic, StoryProgress, Notification):
        db.execute(delete(model).where(model.user_id == user.id))
    # Retain only financial records and a pseudonymous key for accounting and duplicate protection.
    user.name='Deleted account'
    user.settings={'deleted':True}
    user.xp=user.coins=0
    return {'ok':True, 'retained':'Псевдонимизированные платёжные записи для учёта и защиты от повторной обработки'}
