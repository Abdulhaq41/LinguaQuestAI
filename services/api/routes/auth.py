import secrets
from urllib.parse import parse_qs
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..config import settings
from ..db import get_db
from ..models import User, Session as LoginSession
from ..security import verify_init_data, new_session
from ..services.learning import emit

router = APIRouter(prefix='/auth', tags=['Authentication'])
class TelegramAuth(BaseModel):
    init_data: str = Field(max_length=16000)

def login(db, response, uid, name, referral=None):
    user = db.get(User, uid)
    if not user:
        user = User(id=uid, name=name[:100], settings={'referral_code':secrets.token_urlsafe(12)})
        db.add(user)
        db.flush()
        from ..services.referrals import register
        register(db,user,referral)
    if user.settings.get('deleted'):
        user.name=name[:100]
        user.settings={'referral_code':secrets.token_urlsafe(12)}
    if not user.settings.get('referral_code'):
        user.settings={**user.settings,'referral_code':secrets.token_urlsafe(12)}
    response.set_cookie('lq_session', new_session(db, uid), max_age=86400, httponly=True, secure=settings().production, samesite='lax', path='/')
    emit(db, uid, 'app_opened')
    return {'id': uid, 'name': user.name}

@router.post('/telegram')
def authenticate(body: TelegramAuth, response: Response, db: Session = Depends(get_db)):
    if not settings().bot_token: raise HTTPException(503, 'Бот ещё не настроен')
    user = verify_init_data(body.init_data, settings().bot_token)
    return login(db, response, user['id'], user.get('first_name', 'Explorer'),parse_qs(body.init_data).get('start_param',[None])[0])

@router.post('/dev')
def dev(response: Response, db: Session = Depends(get_db)):
    if settings().production or not settings().enable_dev_auth: raise HTTPException(404)
    return login(db, response, -secrets.randbelow(2**40)-1, 'Исследователь')

@router.post('/logout')
def logout(response: Response, lq_session: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    session = db.get(LoginSession, hashlib.sha256((lq_session or '').encode()).hexdigest())
    if session: db.delete(session)
    response.delete_cookie('lq_session')
    return {'ok': True}
