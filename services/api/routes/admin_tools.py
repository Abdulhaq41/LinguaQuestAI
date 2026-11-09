import csv,io,uuid
from typing import Literal,Annotated
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,func,or_,exists
from ..db import get_db,engine
from ..config import settings
from ..security import admin_user
from ..models import User,Payment,Order,Plan,AccessGrant,AdminAudit,AppSetting,Session,Attempt,Word,AIUsage,Notification,now
from ..services.payments import entitlement,paid_entitlement
from ..services.administration import target_user,replay,audit,grant_data,MAX_GIFT_DAYS
router=APIRouter(prefix='/admin',tags=['Administration'])
TelegramID=Annotated[int,Field(ge=-(2**63),le=2**63-1)]

class Action(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    request_id:uuid.UUID
    reason:str=Field(min_length=3,max_length=500)
class GrantCreate(Action):
    user_id:TelegramID
    plan:Literal['START','PRO','ULTRA']='START'
    days:int=Field(default=30,ge=1,le=MAX_GIFT_DAYS)
class Extend(Action):
    days:int=Field(ge=1,le=MAX_GIFT_DAYS)
class Block(Action):
    blocked:bool
class Coins(Action):
    delta:int=Field(ge=-10000,le=10000)
class PauseAI(Action):
    paused:bool


def active_gift():
    return (AccessGrant.revoked_at.is_(None),AccessGrant.starts_at<=now(),AccessGrant.expires_at>now())
def active_paid():
    return (Payment.refunded.is_(False),Payment.grants_access.is_(True),Payment.expires_at>now())
def user_data(db,user):
    return {'id':user.id,'name':user.name,'username':user.settings.get('telegram_username',''),
            'created_at':user.created_at,'xp':user.xp,'coins':user.coins,'is_blocked':user.is_blocked,
            'deleted':bool(user.settings.get('deleted')),'is_admin':user.id in settings().admins,
            'subscription':entitlement(db,user.id),'paid_subscription':paid_entitlement(db,user.id)}

@router.get('/users')
def users(q:str=Query(default='',max_length=100),status:Literal['all','paid','gift','blocked','deleted']='all',
          limit:int=Query(default=25,ge=1,le=100),offset:int=Query(default=0,ge=0),admin=Depends(admin_user),db=Depends(get_db)):
    query=select(User)
    if status=='deleted':query=query.where(User.settings['deleted'].as_boolean().is_(True))
    else:query=query.where(User.settings['deleted'].as_boolean().is_not(True))
    if status=='blocked':query=query.where(User.is_blocked.is_(True))
    if status=='paid':query=query.where(exists(select(Payment.charge_id).where(Payment.user_id==User.id,*active_paid())))
    if status=='gift':query=query.where(exists(select(AccessGrant.id).where(AccessGrant.user_id==User.id,*active_gift())))
    value=q.strip().lstrip('@')
    if value:
        predicates=[User.name.ilike('%'+value+'%'),User.settings['telegram_username'].as_string().ilike('%'+value+'%')]
        if value.lstrip('-').isdigit() and len(value)<=19:
            number=int(value)
            if -(2**63)<=number<2**63:predicates.append(User.id==number)
        query=query.where(or_(*predicates))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[user_data(db,u) for u in db.scalars(query.order_by(User.created_at.desc(),User.id).offset(offset).limit(limit))],
            'total':total,'offset':offset,'limit':limit}

@router.get('/users/{uid}')
def detail(uid:TelegramID,admin=Depends(admin_user),db=Depends(get_db)):
    user=db.get(User,uid)
    if not user:raise HTTPException(404,'Пользователь не найден')
    from .users import progress
    return {**user_data(db,user),'block_reason':user.block_reason,'progress':progress(db,user),
            'language':user.settings.get('language','ru'),'goal':user.settings.get('goal','travel'),
            'timezone':user.settings.get('timezone','Asia/Tashkent'),
            'active_sessions':db.scalar(select(func.count()).select_from(Session).where(Session.user_id==uid,Session.expires_at>now())),
            'words':db.scalar(select(func.count()).select_from(Word).where(Word.user_id==uid)),
            'ai_requests':db.scalar(select(func.count()).select_from(AIUsage).where(AIUsage.user_id==uid,AIUsage.status=='success')),
            'ai_estimated_usd':db.scalar(select(func.coalesce(func.sum(AIUsage.estimated_usd),0)).where(AIUsage.user_id==uid)),
            'grants':[grant_data(g) for g in db.scalars(select(AccessGrant).where(AccessGrant.user_id==uid).order_by(AccessGrant.created_at.desc()))]}

@router.post('/grants')
def create_grant(body:GrantCreate,admin=Depends(admin_user),db=Depends(get_db)):
    user=target_user(db,body.user_id)
    inputs=body.model_dump(mode='json',exclude={'request_id','user_id'})
    previous=replay(db,body.request_id,admin,'grant_created',user.id,inputs)
    if previous is not None:return previous
    if user.settings.get('deleted'):raise HTTPException(409,'Аккаунт удалён; пользователь должен сначала снова войти')
    if not db.get(Plan,body.plan):raise HTTPException(404,'Тариф не найден')
    at=now()
    grant=AccessGrant(id=str(uuid.uuid4()),user_id=user.id,plan_id=body.plan,created_by=admin.id,
                      reason=body.reason,starts_at=at,expires_at=at+body.days*86400,created_at=at)
    db.add(grant);db.flush()
    result=grant_data(grant)
    audit(db,admin,'grant_created',user.id,inputs,result,body.request_id)
    return result


def locked_grant(db,grant_id):
    record=db.get(AccessGrant,grant_id)
    if not record:raise HTTPException(404,'Подарочный доступ не найден')
    target_user(db,record.user_id)
    return db.scalar(select(AccessGrant).where(AccessGrant.id==grant_id).with_for_update().execution_options(populate_existing=True))

@router.post('/grants/{grant_id}/extend')
def extend_grant(grant_id:str,body:Extend,admin=Depends(admin_user),db=Depends(get_db)):
    grant=locked_grant(db,grant_id)
    inputs={**body.model_dump(mode='json',exclude={'request_id'}),'grant_id':grant_id}
    previous=replay(db,body.request_id,admin,'grant_extended',grant.user_id,inputs)
    if previous is not None:return previous
    if grant.revoked_at:raise HTTPException(409,'Отозванный подарок нельзя продлить; создайте новый')
    if db.get(User,grant.user_id).settings.get('deleted'):raise HTTPException(409,'Аккаунт удалён')
    end=max(now(),grant.expires_at)+body.days*86400
    if end>now()+MAX_GIFT_DAYS*86400:raise HTTPException(422,'Подарочный доступ ограничен десятью годами вперёд')
    grant.expires_at=end
    result=grant_data(grant)
    audit(db,admin,'grant_extended',grant.user_id,inputs,result,body.request_id)
    return result

@router.post('/grants/{grant_id}/revoke')
def revoke_grant(grant_id:str,body:Action,admin=Depends(admin_user),db=Depends(get_db)):
    grant=locked_grant(db,grant_id)
    inputs={**body.model_dump(mode='json',exclude={'request_id'}),'grant_id':grant_id}
    previous=replay(db,body.request_id,admin,'grant_revoked',grant.user_id,inputs)
    if previous is not None:return previous
    if not grant.revoked_at:
        grant.revoked_at=now();grant.revoked_by=admin.id;grant.revoke_reason=body.reason
    result=grant_data(grant)
    audit(db,admin,'grant_revoked',grant.user_id,inputs,result,body.request_id)
    return result

@router.get('/grants')
def grants(status:Literal['all','active','expired','revoked']='active',limit:int=Query(default=50,ge=1,le=100),
           offset:int=Query(default=0,ge=0),admin=Depends(admin_user),db=Depends(get_db)):
    query=select(AccessGrant)
    if status=='active':query=query.where(*active_gift())
    if status=='expired':query=query.where(AccessGrant.revoked_at.is_(None),AccessGrant.expires_at<=now())
    if status=='revoked':query=query.where(AccessGrant.revoked_at.is_not(None))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[grant_data(g) for g in db.scalars(query.order_by(AccessGrant.created_at.desc()).offset(offset).limit(limit))],'total':total}

@router.post('/users/{uid}/learning-status')
def learning_status(uid:TelegramID,body:Block,admin=Depends(admin_user),db=Depends(get_db)):
    user=target_user(db,uid)
    inputs=body.model_dump(mode='json',exclude={'request_id'})
    previous=replay(db,body.request_id,admin,'learning_status_changed',uid,inputs)
    if previous is not None:return previous
    if body.blocked and uid in settings().admins:raise HTTPException(409,'Нельзя приостановить обучение администратора')
    user.is_blocked=body.blocked;user.block_reason=body.reason if body.blocked else None
    result={'ok':True,'is_blocked':user.is_blocked}
    audit(db,admin,'learning_status_changed',uid,inputs,result,body.request_id)
    return result

@router.post('/users/{uid}/revoke-sessions')
def revoke_sessions(uid:TelegramID,body:Action,admin=Depends(admin_user),db=Depends(get_db)):
    from sqlalchemy import delete
    target_user(db,uid)
    inputs=body.model_dump(mode='json',exclude={'request_id'})
    previous=replay(db,body.request_id,admin,'sessions_revoked',uid,inputs)
    if previous is not None:return previous
    count=db.execute(delete(Session).where(Session.user_id==uid)).rowcount
    result={'ok':True,'sessions_revoked':count}
    audit(db,admin,'sessions_revoked',uid,inputs,result,body.request_id)
    return result

@router.post('/users/{uid}/coins')
def adjust_coins(uid:TelegramID,body:Coins,admin=Depends(admin_user),db=Depends(get_db)):
    user=target_user(db,uid)
    inputs=body.model_dump(mode='json',exclude={'request_id'})
    previous=replay(db,body.request_id,admin,'coins_adjusted',uid,inputs)
    if previous is not None:return previous
    if not body.delta:raise HTTPException(422,'Укажите ненулевое изменение')
    if user.settings.get('deleted'):raise HTTPException(409,'Аккаунт удалён')
    if user.coins+body.delta<0:raise HTTPException(409,'Баланс монет не может быть отрицательным')
    before=user.coins;user.coins+=body.delta
    result={'ok':True,'before':before,'coins':user.coins}
    audit(db,admin,'coins_adjusted',uid,inputs,result,body.request_id)
    return result

@router.get('/audit')
def journal(action:str=Query(default='',max_length=80),target_id:TelegramID | None=None,
            limit:int=Query(default=50,ge=1,le=100),offset:int=Query(default=0,ge=0),admin=Depends(admin_user),db=Depends(get_db)):
    query=select(AdminAudit)
    if action:query=query.where(AdminAudit.action==action)
    if target_id is not None:query=query.where(AdminAudit.target_id==target_id)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[{'id':a.id,'actor_id':a.actor_id,'target_id':a.target_id,'action':a.action,'details':a.details,'created_at':a.created_at}
                     for a in db.scalars(query.order_by(AdminAudit.created_at.desc(),AdminAudit.id).offset(offset).limit(limit))],'total':total}

@router.get('/system')
def system(admin=Depends(admin_user),db=Depends(get_db)):
    from ..hosted import DEPLOYMENT
    flag=db.get(AppSetting,'ai_paused')
    return {'admin_id':admin.id,'environment':settings().app_env,'database':engine.dialect.name,
            'telegram':dict(DEPLOYMENT),'bot_configured':bool(settings().bot_token),
            'https':settings().webapp_url.startswith('https://'),'ai_configured':settings().ai_enabled and bool(settings().ai_api_key),
            'ai_paused':bool(flag and flag.value.get('paused')),'commerce_enabled':settings().commerce_enabled,
            'voice_available':False,'pro_ultra_sales':False,
            'pending_refunds':db.scalar(select(func.count()).select_from(Payment).where(Payment.refund_pending.is_(True),Payment.refunded.is_(False))),
            'unsent_notifications':db.scalar(select(func.count()).select_from(Notification).where(Notification.sent_at.is_(None))),
            'note':'Секретные значения не отображаются. Голос и продажи PRO/ULTRA закрыты.'}

@router.post('/system/ai-pause')
def pause_ai(body:PauseAI,admin=Depends(admin_user),db=Depends(get_db)):
    db.scalar(select(Plan).where(Plan.id=='START').with_for_update(key_share=True))
    inputs=body.model_dump(mode='json',exclude={'request_id'})
    previous=replay(db,body.request_id,admin,'ai_pause_changed',None,inputs)
    if previous is not None:return previous
    flag=db.get(AppSetting,'ai_paused')
    if not flag:flag=AppSetting(key='ai_paused',value={},updated_by=admin.id);db.add(flag)
    flag.value={'paused':body.paused};flag.updated_by=admin.id;flag.updated_at=now()
    result={'ok':True,'paused':body.paused}
    audit(db,admin,'ai_pause_changed',None,inputs,result,body.request_id)
    return result


def safe_cell(value):
    text=str(value) if value is not None else ''
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text

@router.get('/export/{kind}.csv')
def export_csv(kind:Literal['users','payments'],admin=Depends(admin_user),db=Depends(get_db)):
    out=io.StringIO(newline='');writer=csv.writer(out)
    if kind=='users':
        writer.writerow(['telegram_id','name','username','xp','coins','learning_paused','created_at'])
        for u in db.scalars(select(User).order_by(User.created_at.desc()).limit(5000)):
            writer.writerow([u.id,safe_cell(u.name),safe_cell(u.settings.get('telegram_username','')),u.xp,u.coins,u.is_blocked,u.created_at])
    else:
        writer.writerow(['charge_id','telegram_id','stars','refunded','refund_pending','expires_at','created_at'])
        for p in db.scalars(select(Payment).order_by(Payment.created_at.desc()).limit(5000)):
            writer.writerow([safe_cell(p.charge_id),p.user_id,p.stars,p.refunded,p.refund_pending,p.expires_at,p.created_at])
    audit(db,admin,'csv_exported',inputs={'kind':kind,'limit':5000})
    return Response('\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="linguaquest-{kind}.csv"','Cache-Control':'no-store'})

@router.get('/plans')
def plan_list(admin=Depends(admin_user),db=Depends(get_db)):
    return [{'id':p.id,'stars':p.stars,'enabled':p.enabled,
             'available_for_sale':settings().commerce_enabled and p.enabled and p.id=='START'}
            for p in db.scalars(select(Plan).order_by(Plan.stars))]
