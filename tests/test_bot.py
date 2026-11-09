import time
import pytest
from unittest.mock import AsyncMock
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import Update,Message,Chat
from services.api.config import settings

class FakeTelegramSession(BaseSession):
    def __init__(self):super().__init__();self.calls=[]
    async def close(self):pass
    async def make_request(self,bot,method,timeout=None):
        self.calls.append(method)
        if method.__api_method__ in ('sendMessage','sendPhoto'):return Message(message_id=100,date=int(time.time()),chat=Chat(id=42,type='private'),text=getattr(method,'text',None),caption=getattr(method,'caption',None))
        return True
    async def stream_content(self,*args,**kwargs):
        if False:yield b''

@pytest.mark.asyncio
async def test_aiogram_start_command_no_external_network(monkeypatch):
    from apps.bot.main import dispatcher
    monkeypatch.setattr(settings(),'webapp_url','https://example.test')
    session=FakeTelegramSession()
    bot=Bot('123456:synthetic-test-token',session=session)
    update=Update.model_validate({'update_id':1,'message':{'message_id':1,'date':int(time.time()),'chat':{'id':42,'type':'private'},'from':{'id':42,'is_bot':False,'first_name':'Alex'},'text':'/start','entities':[{'type':'bot_command','offset':0,'length':6}]}})
    await dispatcher().feed_update(bot,update)
    assert len(session.calls)==1
    message=session.calls[0]
    assert 'LinguaQuest AI' in (getattr(message,'text',None) or message.caption)
    assert message.reply_markup.inline_keyboard[0][0].web_app.url=='https://example.test'
    await bot.session.close()
