from datetime import datetime
from zoneinfo import ZoneInfo
import uuid
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select,func
from ..db import get_db
from ..models import Word,Review,Reward,Attempt,Cosmetic,now
from ..security import current_user
from ..services.game import achievements
from ..services.payments import require_paid
from ..services.learning import normalize,emit
router=APIRouter(tags=['Game and vocabulary'])

@router.get('/achievements')
def earned(user=Depends(current_user),db=Depends(get_db)):return achievements(db,user)

@router.get('/vocabulary')
def words(user=Depends(current_user),db=Depends(get_db)):
    return [{'id':w.id,'word':w.word,'translation':w.translation,'due_at':w.due_at,'reviews':w.reviews} for w in db.scalars(select(Word).where(Word.user_id==user.id).order_by(Word.due_at).limit(500))]

@router.post('/vocabulary/review/start')
def review_start(user=Depends(current_user),db=Depends(get_db)):
    require_paid(db,user.id)
    active=db.scalar(select(Review).where(Review.user_id==user.id,Review.answer.is_(None)))
    if active:
        word=db.get(Word,active.word_id)
        return {'id':active.id,'prompt':word.translation}
    word=db.scalar(select(Word).where(Word.user_id==user.id,Word.due_at<=now()).order_by(Word.due_at))
    if not word:return {'done':True,'message':'Все слова повторены. Возвращайтесь позже.'}
    review=Review(id=str(uuid.uuid4()),user_id=user.id,word_id=word.id)
    db.add(review)
    return {'id':review.id,'prompt':word.translation}
class Answer(BaseModel):
    answer:str=Field(min_length=1,max_length=200)
@router.post('/vocabulary/review/{review_id}')
def review_answer(review_id:str,body:Answer,user=Depends(current_user),db=Depends(get_db)):
    require_paid(db,user.id)
    review=db.scalar(select(Review).where(Review.id==review_id,Review.user_id==user.id).with_for_update())
    if not review:raise HTTPException(404)
    word=db.get(Word,review.word_id)
    if review.answer is not None:
        if review.answer!=body.answer:raise HTTPException(409,'Ответ уже сохранён')
    else:
        review.answer=body.answer
        review.correct=normalize(body.answer)==normalize(word.word)
        word.reviews+=1
        word.interval_days=min(60,max(1,word.interval_days*2)) if review.correct else 0
        word.due_at=now()+(word.interval_days*86400 if review.correct else 600)
        emit(db,user.id,'vocabulary_reviewed',correct=review.correct)
    return {'correct':review.correct,'accepted':word.word,'next_review_at':word.due_at}

ITEMS=[{'id':'aqua-frame','title':'Aqua Crystal Frame','coins':30,'color':'#42e4c4'},{'id':'gold-frame','title':'Golden Explorer Frame','coins':70,'color':'#ffc857'},{'id':'violet-frame','title':'Violet Scholar Frame','coins':50,'color':'#9a73ff'}]
@router.get('/shop')
def shop(user=Depends(current_user),db=Depends(get_db)):
    owned=set(db.scalars(select(Cosmetic.item).where(Cosmetic.user_id==user.id)))
    return [{**item,'owned':item['id'] in owned,'equipped':user.settings.get('frame')==item['id']} for item in ITEMS]
@router.post('/shop/{item_id}')
def purchase(item_id:str,user=Depends(current_user),db=Depends(get_db)):
    item=next((item for item in ITEMS if item['id']==item_id),None)
    if not item:raise HTTPException(404)
    owned=db.scalar(select(Cosmetic).where(Cosmetic.user_id==user.id,Cosmetic.item==item_id))
    if not owned:
        if user.coins<item['coins']:raise HTTPException(409,'Недостаточно монет. Пройдите уроки и получите достижения')
        user.coins-=item['coins']
        db.add(Cosmetic(id=str(uuid.uuid4()),user_id=user.id,item=item_id,coins=item['coins']))
        emit(db,user.id,'cosmetic_purchased',item=item_id,coins=item['coins'])
    user.settings={**user.settings,'frame':item_id}
    return {'ok':True,'coins':user.coins,'equipped':item_id}

@router.get('/daily-quest')
def daily(user=Depends(current_user),db=Depends(get_db)):
    tz=ZoneInfo(user.settings.get('timezone','Asia/Tashkent'))
    day=datetime.now(tz).date()
    count=sum(datetime.fromtimestamp(a.completed_at,tz).date()==day for a in db.scalars(select(Attempt).where(Attempt.user_id==user.id,Attempt.completed_at.is_not(None),Attempt.score>=70)))
    claimed=db.scalar(select(Reward).where(Reward.user_id==user.id,Reward.lesson_id=='daily:'+day.isoformat())) is not None
    return {'key':day.isoformat(),'title':'Пройди один урок сегодня','progress':min(count,1),'target':1,'coins':5,'claimed':claimed}
@router.post('/daily-quest/claim')
def claim(user=Depends(current_user),db=Depends(get_db)):
    quest=daily(user,db)
    if quest['progress']<quest['target']:raise HTTPException(409,'Сначала завершите урок')
    if not quest['claimed']:
        db.add(Reward(id=str(uuid.uuid4()),user_id=user.id,lesson_id='daily:'+quest['key'],xp=0,coins=5))
        user.coins+=5
        emit(db,user.id,'daily_quest_completed')
    return {'ok':True,'coins':user.coins}
