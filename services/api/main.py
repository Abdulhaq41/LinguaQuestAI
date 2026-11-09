import secrets, time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from aiogram import Bot
from aiogram.types import Update
from .config import settings
from .routes import auth, users, learning, subscriptions, admin, ai, game, assessment, referrals, analytics

@asynccontextmanager
async def lifespan(app):
    cfg=settings()
    if cfg.production:
        if not cfg.database_url.startswith('postgresql'):raise RuntimeError('Production requires PostgreSQL')
        cfg.admins  # Validate administrator IDs at startup.
        if cfg.enable_dev_auth:raise RuntimeError('Dev authentication must be disabled in production')
        if not cfg.webapp_url.startswith('https://'):raise RuntimeError('Production requires WEBAPP_URL with HTTPS')
        if not cfg.webhook_secret or len(cfg.webhook_secret)<32:raise RuntimeError('Production requires WEBHOOK_SECRET (32+ characters)')
    yield

app=FastAPI(title='LinguaQuest AI',version='0.1.0',lifespan=lifespan)
for router in (auth.router,users.router,learning.router,subscriptions.router,admin.router,ai.router,game.router,assessment.router,referrals.router,analytics.router):app.include_router(router,prefix='/api')
limits=defaultdict(deque)

@app.middleware('http')
async def protections(request:Request,call_next):
    if request.method in ('POST','PATCH','PUT','DELETE') and request.url.path!='/api/telegram/webhook':
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/')!=settings().webapp_url.rstrip('/'):
            return JSONResponse({'detail':'Недопустимый источник запроса'},status_code=403)
        if request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'detail':'Cross-site requests are not allowed'},status_code=403)
    # Defence in depth; production reverse proxy also limits by client IP, across workers.
    key=request.client.host if request.client else 'unknown'
    bucket=limits[key]
    at=time.monotonic()
    while bucket and bucket[0]<at-60:bucket.popleft()
    if request.url.path!='/api/telegram/webhook' and len(bucket)>=180:return JSONResponse({'detail':'Слишком много запросов. Подождите минуту'},status_code=429)
    if request.url.path!='/api/telegram/webhook':bucket.append(at)
    if len(limits)>10000:
        for k in list(limits):
            if not limits[k] or limits[k][-1]<at-60:del limits[k]
    try:content_length=int(request.headers.get('content-length','0'))
    except ValueError:return JSONResponse({'detail':'Invalid Content-Length'},status_code=400)
    if content_length>65536:return JSONResponse({'detail':'Request too large'},status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Cache-Control']='no-store'
    return response

@app.get('/api/health')
def health():
    from sqlalchemy import text
    from .db import SessionLocal
    with SessionLocal() as db:db.execute(text('SELECT 1'))
    return {'status':'ok'}

@app.get('/api/config')
def config():
    cfg=settings()
    return {'development':not cfg.production,'dev_auth':not cfg.production and cfg.enable_dev_auth,'telegram_connected':bool(cfg.bot_token),'ai_connected':cfg.ai_enabled and bool(cfg.ai_api_key),'voice_available':False,'support_contact':cfg.support_contact,'bot_username':cfg.bot_username}

_dp=None
@app.post('/api/telegram/webhook',include_in_schema=False)
async def webhook(request:Request):
    global _dp
    expected=settings().webhook_secret
    if not expected or not secrets.compare_digest(request.headers.get('X-Telegram-Bot-Api-Secret-Token',''),expected):raise HTTPException(403)
    if not settings().bot_token:raise HTTPException(503)
    if _dp is None:
        from apps.bot.main import dispatcher
        _dp=dispatcher()
    update=Update.model_validate(await request.json())
    async with Bot(settings().bot_token) as bot:
        await _dp.feed_update(bot,update)
    return {'ok':True}
