from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from ..security import admin_user
from ..db import get_db
from ..models import User, Payment, Plan, Event, AIUsage, Order, AccessGrant, Attempt, now
from ..services.payments import telegram
from ..services.learning import emit
from ..services.administration import audit
router=APIRouter(prefix='/admin',tags=['Administration'])

@router.get('/dashboard')
def dashboard(admin=Depends(admin_user),db=Depends(get_db)):
    active_events=['app_opened','lesson_started','ai_session_completed']
    activity={label:db.scalar(select(func.count(func.distinct(Event.user_id))).where(Event.kind.in_(active_events),Event.created_at>=now()-days*86400)) for label,days in [('DAU',1),('WAU',7),('MAU',30)]}
    gifted=db.scalar(select(func.count(func.distinct(AccessGrant.user_id))).where(AccessGrant.revoked_at.is_(None),AccessGrant.starts_at<=now(),AccessGrant.expires_at>now()))
    refunded=db.scalar(select(func.coalesce(func.sum(Payment.stars),0)).where(Payment.refunded.is_(True)))
    return {'active_gift_users':gifted,'refunded_stars':refunded,'registered_users':db.scalar(select(func.count()).select_from(User).where(User.settings['deleted'].as_boolean().is_not(True))),'completed_attempts':db.scalar(select(func.count()).select_from(Attempt).where(Attempt.completed_at.is_not(None))),'activity':activity,'users':db.scalar(select(func.count()).select_from(User)), 'gross_stars':db.scalar(select(func.coalesce(func.sum(Payment.stars),0))), 'active_subscribers':db.scalar(select(func.count(func.distinct(Payment.user_id))).where(Payment.expires_at>now(),Payment.refunded.is_(False),Payment.grants_access.is_(True))), 'ai_estimated_usd':db.scalar(select(func.coalesce(func.sum(AIUsage.estimated_usd),0))), 'events':[{'event':kind,'count':count} for kind,count in db.execute(select(Event.kind,func.count()).group_by(Event.kind))], 'note':'Доход в Stars без гарантированного курса вывода. AI-расход — оценка по настроенным ценам, не счёт провайдера.'}

@router.get('/payments')
def payments(admin=Depends(admin_user),db=Depends(get_db)):
    return [{'charge_id':p.charge_id,'user_id':p.user_id,'stars':p.stars,'expires_at':p.expires_at,'refunded':p.refunded,'refund_pending':p.refund_pending} for p in db.scalars(select(Payment).order_by(Payment.created_at.desc()).limit(100))]

class Price(BaseModel):
    stars:int=Field(ge=1,le=10000)
    enabled:bool | None=None
@router.patch('/plans/{plan_id}')
def price(plan_id:str,body:Price,admin=Depends(admin_user),db=Depends(get_db)):
    plan=db.scalar(select(Plan).where(Plan.id==plan_id).with_for_update(key_share=True))
    if not plan: raise HTTPException(404)
    old=plan.stars
    plan.stars=body.stars
    if body.enabled is not None:plan.enabled=body.enabled
    audit(db,admin,'plan_changed',inputs={'plan':plan.id,'stars':plan.stars,'enabled':plan.enabled},result={'previous_stars':old})
    emit(db,admin.id,'admin_price_changed',plan=plan.id,old=old,new=plan.stars)
    return {'ok':True,'note':'Уже выставленные счета и действующие подписки сохраняют исходную цену'}

class Refund(BaseModel):
    charge_id:str=Field(max_length=255)
@router.post('/refund')
async def refund(body:Refund,admin=Depends(admin_user),db=Depends(get_db)):
    payment=db.scalar(select(Payment).where(Payment.charge_id==body.charge_id).with_for_update())
    if not payment: raise HTTPException(404)
    if payment.refunded:return {'ok':True}
    order=db.get(Order,payment.order_id)
    if not order.subscription_canceled and order.initial_charge_id:
        await telegram('editUserStarSubscription',user_id=payment.user_id,telegram_payment_charge_id=order.initial_charge_id,is_canceled=True)
        order.subscription_canceled=True
    await telegram('refundStarPayment',user_id=payment.user_id,telegram_payment_charge_id=payment.charge_id)
    payment.refunded=True
    payment.grants_access=False
    payment.refund_pending=False
    from ..services.referrals import revoke
    revoke(db,payment.charge_id)
    emit(db,admin.id,'admin_refund',charge_id=payment.charge_id)
    audit(db,admin,'payment_refunded',payment.user_id,inputs={'charge_id':payment.charge_id,'stars':payment.stars})
    return {'ok':True}

class ExerciseContent(BaseModel):
    type: str=Field(pattern='^(choice|gap|order|text|correction|dialogue)$')
    prompt: str=Field(min_length=1,max_length=2000)
    answers: list[str]=Field(min_length=1,max_length=20)
    explanation: str=Field(min_length=1,max_length=2000)
    choices: list[str] | None=Field(default=None,max_length=30)
    consequences: dict[str,str] | None=None
class LessonContent(BaseModel):
    id:str=Field(pattern='^[a-z0-9-]{1,80}$')
    title:str=Field(min_length=1,max_length=150)
    description:str=Field(min_length=1,max_length=1000)
    level:str=Field(pattern='^(A1|A2)$')
    chapter:str=Field(min_length=1,max_length=150)
    minutes:int=Field(ge=3,le=15)
    xp:int=Field(ge=10,le=100)
    free:bool=False
    tier:str | None=Field(default=None,pattern='^(START|PRO)$')
    grammar:str=Field(min_length=1,max_length=3000)
    vocabulary:list[dict[str,str]]=Field(max_length=30)
    examples:list[str]=Field(min_length=1,max_length=30)
    exercises:list[ExerciseContent]=Field(min_length=3,max_length=30)
class ContentEdit(BaseModel):
    expected_version:int=Field(ge=0)
    content:LessonContent

@router.get('/lessons')
def lesson_list(admin=Depends(admin_user),db=Depends(get_db)):
    from ..services.learning import all_lessons
    from ..models import ContentVersion
    versions={}
    for version in db.scalars(select(ContentVersion).order_by(ContentVersion.version)):versions[version.lesson_id]=version.version
    return [{'id':key,'version':versions.get(key,0),'content':value} for key,value in all_lessons(db).items()]

@router.put('/lessons/{lesson_id}')
def edit_lesson(lesson_id:str,body:ContentEdit,admin=Depends(admin_user),db=Depends(get_db)):
    import uuid
    from ..models import ContentVersion
    from ..services.learning import normalize
    if body.content.id!=lesson_id:raise HTTPException(422,'ID в адресе и содержимом должны совпадать')
    if body.content.free and lesson_id!='first-hello':raise HTTPException(422,'Бесплатным может быть только первый демоурок')
    for exercise in body.content.exercises:
        if any(len(answer)>500 for answer in exercise.answers):raise HTTPException(422,'Правильный ответ длиннее допустимого пользовательского ввода')
        if not all(answer.strip() for answer in exercise.answers):raise HTTPException(422,'Пустые правильные ответы запрещены')
        if exercise.type in ('choice','gap','dialogue') and (not exercise.choices or not set(exercise.answers)<=set(exercise.choices)):
            raise HTTPException(422,'Для выбора ответа нужны варианты, содержащие все правильные ответы')
    db.scalar(select(Plan).where(Plan.id=='START').with_for_update(key_share=True))
    latest=db.scalar(select(ContentVersion).where(ContentVersion.lesson_id==lesson_id).order_by(ContentVersion.version.desc()).limit(1))
    version=latest.version if latest else 0
    if body.expected_version!=version:raise HTTPException(409,'Контент изменён другим администратором. Перезагрузите список')
    content=body.content.model_dump(exclude_none=True)
    db.add(ContentVersion(id=str(uuid.uuid4()),lesson_id=lesson_id,version=version+1,content=content,admin_id=admin.id,created_at=now()))
    emit(db,admin.id,'admin_content_changed',lesson=lesson_id,version=version+1)
    audit(db,admin,'content_changed',inputs={'lesson_id':lesson_id,'version':version+1})
    return {'ok':True,'version':version+1}
