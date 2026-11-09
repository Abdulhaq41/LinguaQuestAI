"""Register HTTPS webhook without exposing the token in CLI arguments or output."""
import asyncio
from services.api.config import settings
from services.api.services.payments import telegram
async def main():
    cfg=settings()
    if not cfg.webapp_url.startswith('https://') or len(cfg.webhook_secret)<32:raise RuntimeError('HTTPS URL and strong WEBHOOK_SECRET required')
    await telegram('setWebhook',url=cfg.webapp_url.rstrip('/')+'/api/telegram/webhook',secret_token=cfg.webhook_secret,allowed_updates=['message','pre_checkout_query'],drop_pending_updates=False)
    print('Webhook registration confirmed by Telegram')
asyncio.run(main())
