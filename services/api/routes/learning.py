import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from ..db import get_db
from ..models import Attempt, User
from ..security import current_user
from ..services.learning import LESSONS, lesson_or_404, state, answer, complete, emit, all_lessons
from ..services.payments import require_paid, entitlement, require_learning_enabled
router = APIRouter(tags=['Learning'])

@router.get('/learning-path')
def path(user: User = Depends(current_user), db=Depends(get_db)):
    sub = entitlement(db, user.id)
    completed = set(db.scalars(select(Attempt.lesson_id).where(Attempt.user_id == user.id, Attempt.completed_at.is_not(None), Attempt.score >= 70)))
    items=all_lessons(db)
    preferred=['first-hello','daily-routine','cafe','directions','future-plans','yesterday'] if user.settings.get('goal') in ('work','study') else list(items)
    if user.settings.get('assessment',{}).get('level')=='A2 practice':preferred=['first-hello','yesterday','future-plans','cafe','daily-routine','directions']
    ordered=[items[key] for key in dict.fromkeys([*preferred,*items]) if key in items]
    return [{'id': l['id'], 'title': l['title'], 'level': l['level'], 'chapter': l['chapter'], 'description': l['description'], 'minutes': l['minutes'], 'xp': l['xp'], 'free': l['free'], 'locked': not l['free'] and (sub is None or (l.get('tier')=='PRO' and sub['plan']=='START')), 'completed': l['id'] in completed} for l in ordered]

def access(db, user, lesson):
    require_learning_enabled(user)
    if not user.settings.get('onboarded'): raise HTTPException(409, 'Сначала сохраните учебную цель в профиле')
    if not lesson['free']: require_paid(db, user.id, ai=lesson.get('tier') == 'PRO')

@router.post('/lessons/{lesson_id}/start')
def start(lesson_id: str, user: User = Depends(current_user), db=Depends(get_db)):
    lesson = lesson_or_404(lesson_id,db)
    access(db, user, lesson)
    attempt = db.scalar(select(Attempt).where(Attempt.user_id == user.id, Attempt.lesson_id == lesson_id, Attempt.completed_at.is_(None)).order_by(Attempt.started_at.desc()))
    if not attempt:
        attempt = Attempt(id=str(uuid.uuid4()), user_id=user.id, lesson_id=lesson_id, answers=[], content_snapshot=lesson)
        db.add(attempt)
        db.flush()
        emit(db, user.id, 'lesson_started', lesson=lesson_id)
    return {**state(attempt), 'intro': {k:lesson.get(k) for k in ('title', 'vocabulary', 'grammar', 'examples','scene','actor')}}

class Answer(BaseModel):
    index: int = Field(ge=0, le=100)
    value: str = Field(min_length=1, max_length=500)

@router.post('/attempts/{attempt_id}/answer')
def submit(attempt_id: str, body: Answer, user: User=Depends(current_user), db=Depends(get_db)):
    attempt = db.get(Attempt, attempt_id)
    if not attempt or attempt.user_id != user.id: raise HTTPException(404)
    access(db, user, attempt.content_snapshot or lesson_or_404(attempt.lesson_id,db))
    return answer(db, user, attempt_id, body.index, body.value)

@router.post('/attempts/{attempt_id}/complete')
def finish(attempt_id: str, user: User=Depends(current_user), db=Depends(get_db)):
    attempt = db.get(Attempt, attempt_id)
    if not attempt or attempt.user_id != user.id: raise HTTPException(404)
    access(db, user, attempt.content_snapshot or lesson_or_404(attempt.lesson_id,db))
    return complete(db, user, attempt_id)
