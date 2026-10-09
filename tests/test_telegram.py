import asyncio
from io import StringIO
import logging
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, User
from aiogram.types import Update
from aiogram.client.session.base import BaseSession

from app.config import Config
from app.handlers.telegram import LimitedBuffer, TelegramHandler, create_dispatcher
from app.logging_setup import SecretFilter
from app.services.access import BotError
from tests.test_training import training


def fake_message(user=2, chat=-100, text="8*50", message_id=50, **extra):
    return Message(message_id=message_id, date=0, chat=Chat(id=chat, type="supergroup"), from_user=User(id=user, is_bot=False, first_name="Спортсмен"), text=text, **extra)


def test_adapter_result_and_ordinary_chat(db, training, monkeypatch):
    handler = TelegramHandler(db, Config(bot_token="123:secret", owner_telegram_id=1))
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    asyncio.run(handler.message(fake_message(text="хорошая тренировка")))
    asyncio.run(handler.message(fake_message(text="я сделал 8*50")))
    answer.assert_not_called()
    asyncio.run(handler.message(fake_message()))
    assert "✓ xRust" in answer.call_args.args[0]
    assert "подход 2/4" in training.status(-100, 2).text
    asyncio.run(handler.message(fake_message(user=3, chat=-999)))
    assert "чат не настроен" in answer.call_args.args[0]


def test_reply_cannot_bind_another_user(db, training, monkeypatch):
    handler = TelegramHandler(db, Config(bot_token="123:secret", owner_telegram_id=1))
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    asyncio.run(handler.message(fake_message(user=4, text="/bind xrust", reply_to_message=fake_message(user=2))))
    assert "уже привязан" in answer.call_args.args[0]
    assert "Вы не привязаны" in handler.bindings.whoami(-100, 4)


def test_download_buffer_limits_actual_bytes():
    buffer = LimitedBuffer()
    with pytest.raises(BotError):
        buffer.write(b"x" * (128 * 1024 + 1))


def test_command_for_another_bot_ignored(db, training, monkeypatch):
    handler = TelegramHandler(db, Config(bot_token="123:secret", owner_telegram_id=1))
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    monkeypatch.setattr(Bot, "me", AsyncMock(return_value=User(id=123, is_bot=True, first_name="Бот", username="gym_bot")))
    bot = Bot("123:secret")
    async def run():
        try:
            await handler.message(fake_message(text="/skip@other_bot").as_(bot))
            answer.assert_not_called()
            assert "Жим" in training.status(-100, 2).text
            await handler.message(fake_message(text="/status@GYM_BOT").as_(bot))
            assert "Жим" in answer.call_args.args[0]
        finally:
            await bot.session.close()
    asyncio.run(run())


def test_token_redacted_in_exception():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretFilter("TOKEN"))
    logger = logging.getLogger("test_secret")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        try:
            raise ValueError("URL/TOKEN/path")
        except ValueError:
            logger.exception("Ошибка %s", "TOKEN")
        assert "TOKEN" not in stream.getvalue()
        assert "[СКРЫТО]" in stream.getvalue()
    finally:
        logger.removeHandler(handler)


def test_dispatcher_routes_update_and_callback(db, training):
    class OfflineSession(BaseSession):
        def __init__(self):
            super().__init__()
            self.sent = []
        async def close(self):
            pass
        async def make_request(self, bot, method, timeout=None):
            self.sent.append(method)
            return True
        async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
            if False:
                yield b""
    session = OfflineSession()
    bot = Bot("123:secret", session=session)
    dispatcher = create_dispatcher(db, Config(bot_token="123:secret", owner_telegram_id=1))
    async def run():
        await dispatcher.feed_update(bot, Update(update_id=1, message=fake_message()))
        await dispatcher.feed_update(bot, Update(update_id=2, message=fake_message(text="/finish_train", message_id=51)))
        finish_message = session.sent[-1]
        token = finish_message.reply_markup.inline_keyboard[0][0].callback_data
        from aiogram.types import CallbackQuery
        callback = CallbackQuery(id="callback1", from_user=User(id=2, is_bot=False, first_name="Спортсмен"), chat_instance="test", message=fake_message(user=123, text="Подтвердите", message_id=52), data=token)
        await dispatcher.feed_update(bot, Update(update_id=3, callback_query=callback))
        assert "Тренировка завершена" in session.sent[-1].text
        await bot.session.close()
    asyncio.run(run())
