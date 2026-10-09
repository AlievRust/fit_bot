"""Настоящий цикл aiogram с имитацией Telegram для проверки SIGTERM без сети."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, GetUpdates
from aiogram.types import User

import app.bot as runtime
from app.config import Config


class OfflineSession(BaseSession):
    async def close(self):
        logging.info("event=http_session_closed")

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, GetMe):
            return User(id=123, is_bot=True, first_name="Тестовый бот", username="offline_gym_bot")
        if isinstance(method, GetUpdates):
            logging.info("event=offline_polling_wait")
            await asyncio.sleep(3600)
            return []
        raise RuntimeError("Неожиданный метод тестового транспорта")

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        if False:
            yield b""


logging.basicConfig(level=logging.INFO, format="%(message)s")
runtime.Bot = lambda token: Bot(token, session=OfflineSession())
asyncio.run(runtime.run(Config(bot_token="123:test", owner_telegram_id=1, database_path=Path("/tmp/shutdown.sqlite3"))))
