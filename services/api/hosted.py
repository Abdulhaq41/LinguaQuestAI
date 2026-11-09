"""Single-container hosting: API and built Mini App share one HTTPS origin."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .config import settings
from .services.payments import telegram

logger = logging.getLogger(__name__)
DEPLOYMENT = {'telegram': 'not_configured'}

async def configure_telegram():
    cfg = settings()
    if not cfg.bot_token:
        DEPLOYMENT['telegram'] = 'not_configured'
        return
    if not cfg.bot_username or not cfg.webapp_url.startswith('https://') or len(cfg.webhook_secret) < 32:
        raise RuntimeError('BOT_USERNAME, HTTPS WEBAPP_URL and WEBHOOK_SECRET are required')
    identity = await telegram('getMe')
    if identity.get('username', '').casefold() != cfg.bot_username.lstrip('@').casefold():
        raise RuntimeError('BOT_USERNAME does not match the configured bot')
    url = cfg.webapp_url.rstrip('/')
    await telegram('setWebhook', url=url+'/api/telegram/webhook', secret_token=cfg.webhook_secret,
                   allowed_updates=['message', 'pre_checkout_query'], drop_pending_updates=False)
    await telegram('setChatMenuButton', menu_button={'type': 'web_app', 'text': 'LinguaQuest',
                                                   'web_app': {'url': url}})
    commands = {'start': 'Начать приключение', 'app': 'Открыть приложение', 'profile': 'Мой прогресс',
                'subscription': 'Подписка', 'referral': 'Пригласить друзей', 'settings': 'Настройки',
                'help': 'Помощь', 'paysupport': 'Помощь с оплатой', 'privacy': 'Конфиденциальность', 'terms': 'Условия'}
    await telegram('setMyCommands', commands=[{'command': k, 'description': v} for k, v in commands.items()])
    DEPLOYMENT['telegram'] = 'ready'
    logger.info('Telegram webhook and Mini App menu configured')

async def configure_after_start():
    # Lifespan must return before Telegram can connect to the public webhook.
    import httpx
    DEPLOYMENT['telegram'] = 'pending'
    async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
        for _ in range(60):
            try:
                response = await client.get(f'http://127.0.0.1:{int(os.environ.get("PORT", "8000"))}/api/health')
                if response.is_success:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            DEPLOYMENT['telegram'] = 'failed'
            logger.error('Local API readiness failed before Telegram setup')
            return
    for delay in (2, 5, 15, 30, 60):
        try:
            await configure_telegram()
            return
        except Exception:
            # Never print provider exceptions: their URLs can include the bot token.
            logger.warning('Telegram setup failed; check token, bot username and public HTTPS availability')
            await asyncio.sleep(delay)
    DEPLOYMENT['telegram'] = 'failed'


def attach_frontend(app: FastAPI, root: Path):
    if not (root / 'index.html').is_file():
        raise RuntimeError('Mini App build is missing')
    lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def hosted_lifespan(instance):
        async with lifespan(instance):
            task = None
            if os.environ.get('AUTO_CONFIGURE_BOT', 'false').lower() == 'true':
                task = asyncio.create_task(configure_after_start())
            try:
                yield
            finally:
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
    app.router.lifespan_context = hosted_lifespan

    @app.middleware('http')
    async def browser_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' https://telegram.org; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; "
            "connect-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org; "
            "base-uri 'self'; form-action 'self'")
        if settings().production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.get('/api/deployment/status')
    def deployment_status():
        return dict(DEPLOYMENT)

    # Keep API routes before StaticFiles. Source content with answers is never served.
    app.mount('/', StaticFiles(directory=root, html=True), name='miniapp')
    return app


def create_app():
    from .main import app
    root = Path(os.environ.get('MINIAPP_DIST', str(Path(__file__).resolve().parents[2] / 'web')))
    return attach_frontend(app, root)
