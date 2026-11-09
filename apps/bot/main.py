import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery, FSInputFile
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.models import User, Payment, Order
from services.api.services.payments import validate_checkout, apply_payment, entitlement
from sqlalchemy import select

router=Router()

def app_keyboard():
    url=settings().webapp_url.rstrip('/')
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🚀 Начать приключение',web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text='💎 Подписка',web_app=WebAppInfo(url=url+'?section=plans')),InlineKeyboardButton(text='🎯 Мой прогресс',web_app=WebAppInfo(url=url+'?section=profile'))],
        [InlineKeyboardButton(text='👥 Пригласить друзей',web_app=WebAppInfo(url=url+'?section=learn&tool=referral')),InlineKeyboardButton(text='❓ Помощь',callback_data='help')]])

@router.message(Command('id'))
async def identity(message:Message):
    if message.from_user:
        await message.answer(f'Ваш Telegram ID: {message.from_user.id}\nЭто ID аккаунта, не токен. Для доступа владельца укажите его в ADMIN_TELEGRAM_IDS на хостинге.')

@router.message(Command('admin'))
async def admin_entry(message:Message):
    if not message.from_user or message.from_user.id not in settings().admins:
        await message.answer('Админка доступна только назначенным администраторам. Ваш ID можно посмотреть командой /id.')
        return
    keyboard=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Панель администратора',web_app=WebAppInfo(url=settings().webapp_url.rstrip('/')+'?section=admin'))]])
    await message.answer('Управление пользователями, подарочными подписками и контентом.',reply_markup=keyboard)

@router.message(Command('start','app'))
async def start(message:Message):
    text='🌍 Добро пожаловать в LinguaQuest AI!\n\nИзучай язык. Проживи приключение.\n🎮 Короткие игровые уроки\n✨ Личный прогресс и XP\n💎 Первый урок бесплатно, затем START: 89 Stars / 30 дней. Актуальная цена — в приложении.\n\nОткрой Mini App и познакомься с Lexi!'
    image=Path(__file__).resolve().parents[2]/'assets'/'mascots'/'lexi-generated.png'
    if image.exists():await message.answer_photo(FSInputFile(image),caption=text,reply_markup=app_keyboard())
    else:await message.answer(text,reply_markup=app_keyboard())

@router.message(Command('profile','settings','subscription','referral'))
async def profile(message:Message):
    await message.answer('Прогресс, тарифы, отмена продления и настройки доступны в профиле приложения. Приглашения и реферальные бонусы — в разделе обучения приложения.',reply_markup=app_keyboard())

@router.callback_query(F.data=='help')
async def help_callback(query:CallbackQuery):
    await query.answer()
    if query.message:await query.message.answer('Поддержка: '+(settings().support_contact or 'Контакт пока не настроен владельцем.'))

@router.message(Command('help','paysupport'))
async def help_command(message:Message):
    await message.answer('Поддержка: '+(settings().support_contact or 'Контакт поддержки ещё не настроен владельцем.')+'\nДля вопроса об оплате укажите идентификатор операции из истории платежей. Не присылайте пароли и ключи.')

@router.message(Command('privacy','terms'))
async def legal(message:Message):
    await message.answer('Условия и политика доступны по кнопке «Документы» в приложении. До запуска требуется юридическая проверка.',reply_markup=app_keyboard())

@router.pre_checkout_query()
async def pre_checkout(query:PreCheckoutQuery):
    with SessionLocal() as db:
        if settings().database_url.startswith('sqlite'):db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        ok=validate_checkout(db,query.model_dump(by_alias=True))
        db.commit()
    await query.answer(ok=ok,error_message=None if ok else 'Счёт устарел или уже используется. Откройте подписку в приложении.')

@router.message(F.successful_payment)
async def paid(message:Message):
    with SessionLocal() as db:
        if settings().database_url.startswith('sqlite'):db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        activated=apply_payment(db,message.from_user.id,message.successful_payment.model_dump())
        db.commit()
        payment=db.get(Payment,message.successful_payment.telegram_payment_charge_id)
        if payment.refund_pending:
            from services.api.services.payments import telegram
            order=db.get(Order,payment.order_id)
            if not order.subscription_canceled and order.initial_charge_id:
                await telegram('editUserStarSubscription',user_id=payment.user_id,telegram_payment_charge_id=order.initial_charge_id,is_canceled=True)
                order.subscription_canceled=True
            await telegram('refundStarPayment',user_id=payment.user_id,telegram_payment_charge_id=payment.charge_id)
            payment.refunded=True;payment.refund_pending=False;payment.grants_access=False
            db.commit()
            await message.answer('Обнаружена параллельная подписка. Лишний платёж возвращён; текущий доступ сохранён.')
            return
    if not activated:return
    await message.answer('✨ Оплата подтверждена Telegram. Доступ активирован. Спасибо!',reply_markup=app_keyboard())

@router.message(F.refunded_payment)
async def refunded(message:Message):
    with SessionLocal() as db:
        payment=db.scalar(select(Payment).where(Payment.charge_id==message.refunded_payment.telegram_payment_charge_id).with_for_update())
        if payment:
            payment.refunded=True;payment.refund_pending=False;payment.grants_access=False
            from services.api.services.referrals import revoke
            revoke(db,payment.charge_id)
            db.commit()
            order=db.get(Order,payment.order_id)
            if not order.subscription_canceled and order.initial_charge_id:
                from services.api.services.payments import telegram
                await telegram('editUserStarSubscription',user_id=payment.user_id,telegram_payment_charge_id=order.initial_charge_id,is_canceled=True)
                order.subscription_canceled=True
        db.commit()

def dispatcher():
    dp=Dispatcher()
    dp.include_router(router)
    return dp

async def main():
    if not settings().bot_token:raise RuntimeError('BOT_TOKEN is required')
    bot=Bot(settings().bot_token)
    await dispatcher().start_polling(bot)

if __name__=='__main__':asyncio.run(main())
