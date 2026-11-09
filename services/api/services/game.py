from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import uuid
from sqlalchemy import select,func
from ..models import Attempt,Word,Review,Achievement,StoryProgress,Reward,now
from .learning import emit

def stats(db,user):
    attempts=list(db.scalars(select(Attempt).where(Attempt.user_id==user.id,Attempt.completed_at.is_not(None),Attempt.score>=70)))
    tz=ZoneInfo(user.settings.get('timezone','Asia/Tashkent'))
    dates={datetime.fromtimestamp(a.completed_at,tz).date() for a in attempts}
    day=datetime.now(tz).date()
    if day not in dates:day-=timedelta(days=1)
    streak=0
    while day in dates:streak+=1;day-=timedelta(days=1)
    return {'lessons':len({a.lesson_id for a in attempts if not a.lesson_id.startswith(('life-','boss-'))}),'perfect':len({a.lesson_id for a in attempts if a.score==100}),'words':db.scalar(select(func.count()).select_from(Word).where(Word.user_id==user.id)),'reviews':db.scalar(select(func.count()).select_from(Review).where(Review.user_id==user.id,Review.correct.is_(True))),'streak':streak,'stories':len({a.lesson_id for a in attempts if a.lesson_id.startswith('life-')}),'bosses':len({a.lesson_id for a in attempts if a.lesson_id.startswith('boss-')}),'xp':user.xp,'days':len(dates)}

CATALOG=[]
for metric,thresholds,titles in [
 ('lessons',[1,2,3,4,6],['First Step','New Explorer','City Learner','Chapter Keeper','Quest Scholar']),
 ('perfect',[1,2,3],['Perfect Start','Sharp Eye','Grammar Hero']),
 ('words',[3,10,20,50,100],['Word Seed','Word Collector','Word Hunter','Lexicon Keeper','Vocabulary Master']),
 ('reviews',[1,10,50],['Recall','Memory Builder','Memory Master']),
 ('streak',[3,7,14,30],['Three Sparks','Seven Days','Two Weeks','A Month of Discovery']),
 ('stories',[1,4,8],['Traveler','City Guide','London Explorer']),
 ('bosses',[1,3],['Boss Slayer','Chapter Champion'])]:
    for threshold,title in zip(thresholds,titles):CATALOG.append({'id':f'{metric}-{threshold}','title':title,'metric':metric,'threshold':threshold,'description':f'{metric}: {threshold}','coins':5,'rarity':'rare' if threshold>=10 else 'common'})

def achievements(db,user):
    numbers=stats(db,user)
    earned={a.key:a.created_at for a in db.scalars(select(Achievement).where(Achievement.user_id==user.id))}
    for item in CATALOG:
        if item['id'] not in earned and numbers[item['metric']]>=item['threshold']:
            db.add(Achievement(id=str(uuid.uuid4()),user_id=user.id,key=item['id']))
            user.coins+=item['coins']
            earned[item['id']]=now()
            emit(db,user.id,'achievement_unlocked',achievement=item['id'])
    db.flush()
    return [{**item,'earned_at':earned.get(item['id']),'progress':min(numbers[item['metric']],item['threshold'])} for item in CATALOG]

def introduce_words(db,user,lesson):
    existing=set(db.scalars(select(Word.word).where(Word.user_id==user.id)))
    for word in lesson['vocabulary']:
        if word['word'] not in existing:
            db.add(Word(id=str(uuid.uuid4()),user_id=user.id,word=word['word'],translation=word.get(user.settings.get('language','ru'),word['ru'])))
            existing.add(word['word'])
    db.flush()
