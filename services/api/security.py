import hashlib, hmac, json, secrets, time
from urllib.parse import parse_qsl
from fastapi import Depends, HTTPException, Cookie
from sqlalchemy import select
from sqlalchemy.orm import Session as DB
from .db import get_db
from .models import Session, User
from .config import settings

def verify_init_data(raw: str, bot_token: str, at: int | None = None):
    try:
        pairs = parse_qsl(raw, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs): raise ValueError('duplicate fields')
        received = fields.pop('hash')
        check = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
        key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received, expected): raise ValueError('signature')
        age = (at or int(time.time())) - int(fields['auth_date'])
        if age < -30 or age > 300: raise ValueError('expired')
        user = json.loads(fields['user'])
        if not isinstance(user['id'], int) or user['id'] <= 0: raise ValueError('user')
        return user
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, 'Недействительная или устаревшая сессия Telegram')

def current_user(lq_session: str | None = Cookie(default=None), db: DB = Depends(get_db)):
    token = hashlib.sha256((lq_session or '').encode()).hexdigest()
    session = db.get(Session, token)
    if not session or session.expires_at <= int(time.time()):
        raise HTTPException(401, 'Откройте приложение заново из Telegram')
    user = db.scalar(select(User).where(User.id == session.user_id).with_for_update())
    if not user: raise HTTPException(401, 'Аккаунт не найден')
    return user

def admin_user(user: User = Depends(current_user)):
    if user.id not in settings().admins: raise HTTPException(403, 'Требуются права администратора')
    return user

def new_session(db, user_id):
    raw = secrets.token_urlsafe(48)
    db.add(Session(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user_id=user_id, expires_at=int(time.time())+86400))
    return raw
