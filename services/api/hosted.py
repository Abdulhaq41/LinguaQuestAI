"""Single-container hosting: API and built Mini App share one HTTPS origin."""
import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .config import settings
from .services.payments import telegram, TelegramRequestError

logger = logging.getLogger(__name__)
DEPLOYMENT = {'telegram': 'not_configured'}

class TelegramSetupError(RuntimeError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def set_deployment(status, **metadata):
    DEPLOYMENT.clear()
    DEPLOYMENT.update(telegram=status, **metadata)


async def setup_request(method, **data):
    DEPLOYMENT['step'] = method
    result = await telegram(method, **data)
    if method != 'getMe' and result is not True:
        raise TelegramSetupError('configuration_not_confirmed', 'Telegram did not confirm configuration')
    return result


async def configure_telegram():
    cfg = settings()
    if not cfg.bot_token:
        set_deployment('not_configured', error='missing_bot_token', step='configuration')
        return
    DEPLOYMENT['step'] = 'configuration'
    if not cfg.bot_username:
        raise TelegramSetupError('missing_bot_username', 'BOT_USERNAME is required')
    if not cfg.webapp_url.startswith('https://'):
        raise TelegramSetupError('https_url_required', 'HTTPS WEBAPP_URL is required')
    if len(cfg.webhook_secret) < 32:
        raise TelegramSetupError('weak_webhook_secret', 'WEBHOOK_SECRET requires at least 32 characters')
    identity = await setup_request('getMe')
    if not isinstance(identity, dict) or not isinstance(identity.get('username'), str):
        raise TelegramSetupError('invalid_bot_identity', 'Bot API returned an invalid identity')
    if identity.get('username', '').casefold() != cfg.bot_username.lstrip('@').casefold():
        raise TelegramSetupError('bot_username_mismatch', 'BOT_USERNAME does not match the configured bot')
    url = cfg.webapp_url.rstrip('/')
    await setup_request('setWebhook', url=url+'/api/telegram/webhook', secret_token=cfg.webhook_secret,
                   allowed_updates=['message', 'pre_checkout_query'], drop_pending_updates=False)
    await setup_request('setChatMenuButton', menu_button={'type': 'web_app', 'text': 'LinguaQuest',
                                                   'web_app': {'url': url}})
    commands = {'start': 'Начать приключение', 'app': 'Открыть приложение', 'profile': 'Мой прогресс',
                'subscription': 'Подписка', 'referral': 'Пригласить друзей', 'settings': 'Настройки',
                'help': 'Помощь', 'paysupport': 'Помощь с оплатой', 'privacy': 'Конфиденциальность', 'terms': 'Условия'}
    await setup_request('setMyCommands', commands=[{'command': k, 'description': v} for k, v in commands.items()])
    set_deployment('ready')
    logger.info('Telegram webhook and Mini App menu configured')

async def configure_after_start():
    # Lifespan must return before Telegram can connect to the public webhook.
    import httpx
    set_deployment('pending', step='health_check')
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
            set_deployment('failed', step='health_check', error='local_api_not_ready')
            logger.error('Local API readiness failed before Telegram setup')
            return
    retry_delays = (2, 5, 15, 30)
    for attempt in range(1, 6):
        try:
            await configure_telegram()
            return
        except TelegramSetupError as exc:
            set_deployment('failed', step=DEPLOYMENT.get('step', 'configuration'), error=exc.reason)
            logger.error('Telegram setup stopped: reason=%s', exc.reason)
            return
        except TelegramRequestError as exc:
            permanent = exc.reason in {'invalid_bot_token', 'invalid_bot_token_format', 'telegram_forbidden', 'bot_api_not_found',
                                       'invalid_webhook_secret', 'request_rejected'}
            final = permanent or attempt == 5
            metadata = {'step': DEPLOYMENT.get('step', 'unknown'), 'error': exc.reason, 'attempt': attempt}
            if exc.upstream_status is not None:
                metadata['http_status'] = exc.upstream_status
            set_deployment('failed' if final else 'pending', **metadata)
            logger.warning('Telegram setup: step=%s reason=%s attempt=%s',
                           metadata['step'], exc.reason, attempt)
            if final:
                return
            # Honor Telegram's Retry-After rather than repeating immediately.
            await asyncio.sleep(max(retry_delays[attempt-1], exc.retry_after or 0))
        except Exception:
            # Never include provider exceptions or request data in logs or public status.
            set_deployment('failed', step=DEPLOYMENT.get('step', 'unknown'), error='internal_setup_error')
            logger.error('Telegram setup failed with an internal error')
            return


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
            else:
                set_deployment('not_configured', error='auto_configuration_disabled')
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
        result = dict(DEPLOYMENT)
        revision = os.environ.get('RENDER_GIT_COMMIT', '')
        if result['telegram'] != 'ready' and re.fullmatch(r'[0-9a-fA-F]{7,64}', revision):
            result['revision'] = revision[:7]
        return result

    # Keep API routes before StaticFiles. Source content with answers is never served.
    app.mount('/', StaticFiles(directory=root, html=True), name='miniapp')
    return app


def create_app():
    from .main import app
    root = Path(os.environ.get('MINIAPP_DIST', str(Path(__file__).resolve().parents[2] / 'web')))
    return attach_frontend(app, root)
