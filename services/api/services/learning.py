import json, re, uuid
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select
from ..models import Attempt, Reward, Event, ContentVersion, now

CONTENT = Path(__file__).resolve().parents[3] / 'content' / 'lessons'
ORDER = ['first-hello', 'cafe', 'daily-routine', 'directions', 'yesterday', 'future-plans']
ORDER += ['life-'+x for x in ['airport','transport','neighbor','hotel','market','job','interview','office']]
ORDER += ['boss-airport','boss-city','boss-work']
LESSONS = {key: json.loads((CONTENT / (key+'.json')).read_text()) for key in ORDER}

def emit(db, uid, kind, **data):
    db.add(Event(id=str(uuid.uuid4()), user_id=uid, kind=kind, data=data))

def all_lessons(db):
    result = dict(LESSONS)
    for version in db.scalars(select(ContentVersion).order_by(ContentVersion.version)):
        result[version.lesson_id] = version.content
    return result

def lesson_or_404(lesson_id, db=None):
    if db is not None:
        version = db.scalar(select(ContentVersion).where(ContentVersion.lesson_id==lesson_id).order_by(ContentVersion.version.desc()).limit(1))
        if version:return version.content
    if lesson_id not in LESSONS: raise HTTPException(404, 'Урок не найден')
    return LESSONS[lesson_id]

def normalize(answer):
    return re.sub(r'[^\w\s]', '', answer.casefold().replace('’', "'")).strip()

def public_exercise(exercise):
    return {k:v for k,v in exercise.items() if k not in ('answers', 'explanation', 'consequences')}

def state(attempt):
    lesson = attempt.content_snapshot or LESSONS[attempt.lesson_id]
    index = len(attempt.answers)
    return {'id': attempt.id, 'lesson_id': attempt.lesson_id, 'index': index, 'total': len(lesson['exercises']), 'exercise': public_exercise(lesson['exercises'][index]) if index < len(lesson['exercises']) else None, 'completed': attempt.completed_at is not None, 'score': attempt.score}

def answer(db, user, attempt_id, index, value):
    attempt = db.scalar(select(Attempt).where(Attempt.id == attempt_id, Attempt.user_id == user.id).with_for_update())
    if not attempt: raise HTTPException(404, 'Попытка не найдена')
    if index < len(attempt.answers):
        previous = attempt.answers[index]
        if previous['value'] != value: raise HTTPException(409, 'Ответ на этот вопрос уже сохранён')
        return {**previous, 'state': state(attempt)}
    if attempt.completed_at or index != len(attempt.answers): raise HTTPException(409, 'Обновите состояние урока')
    lesson = attempt.content_snapshot or LESSONS[attempt.lesson_id]
    if index >= len(lesson['exercises']): raise HTTPException(409, 'Завершите урок')
    ex = lesson['exercises'][index]
    result = {'value': value, 'correct': normalize(value) in {normalize(x) for x in ex['answers']}, 'explanation': ex['explanation'], 'accepted': ex['answers'][0]}
    if ex.get('consequences', {}).get(value): result['explanation'] += ' '+ex['consequences'][value]
    attempt.answers = [*attempt.answers, result]
    db.flush()
    return {**result, 'state': state(attempt)}

def complete(db, user, attempt_id):
    attempt = db.scalar(select(Attempt).where(Attempt.id == attempt_id, Attempt.user_id == user.id).with_for_update())
    if not attempt: raise HTTPException(404, 'Попытка не найдена')
    lesson = attempt.content_snapshot or LESSONS[attempt.lesson_id]
    if len(attempt.answers) != len(lesson['exercises']): raise HTTPException(409, 'Сначала ответьте на все вопросы')
    reward = db.scalar(select(Reward).where(Reward.user_id == user.id, Reward.lesson_id == lesson['id']))
    awarded = 0
    if attempt.completed_at is None:
        attempt.completed_at = now()
        attempt.score = round(sum(x['correct'] for x in attempt.answers) / len(attempt.answers) * 100)
        if attempt.score >= 70 and not reward:
            awarded = lesson['xp']
            db.add(Reward(id=str(uuid.uuid4()), user_id=user.id, lesson_id=lesson['id'], xp=awarded, coins=10))
            user.xp += awarded
            user.coins += 10
            from .game import introduce_words, achievements
            introduce_words(db, user, lesson)
            achievements(db, user)
        emit(db, user.id, 'lesson_completed', lesson=lesson['id'], score=attempt.score, xp=awarded)
    return {'score': attempt.score, 'xp_awarded': awarded, 'total_xp': user.xp, 'passed': attempt.score >= 70, 'feedback': 'Отлично! Тема освоена.' if attempt.score >= 70 else 'Повторите примеры и попробуйте ещё раз. Новая попытка бесплатна.', 'mistakes': [x for x in attempt.answers if not x['correct']]}
