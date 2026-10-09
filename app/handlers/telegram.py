"""Тонкий Telegram-адаптер; бизнес-правила живут в сервисах."""

import logging
import re
from io import BytesIO

from aiogram import Dispatcher, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.exc import SQLAlchemyError

from app.services.access import BotError
from app.services.bindings import Bindings
from app.services.programs import Programs
from app.parsers.program import MAX_IMPORT_BYTES
from app.services.training import Training
from app.handlers.views import Reply

logger = logging.getLogger(__name__)


class LimitedBuffer(BytesIO):
    def write(self, data):
        if self.tell() + len(data) > MAX_IMPORT_BYTES:
            raise BotError("YAML не должен превышать 128 КиБ.")
        return super().write(data)


def command_parts(text: str) -> tuple[str, str]:
    parts = text.strip().split(maxsplit=1)
    return (parts[0].split("@", 1)[0].lower() if parts else "", parts[1].strip() if len(parts) > 1 else "")


class TelegramHandler:
    def __init__(self, db, config):
        self.bindings = Bindings(db, config.owner_telegram_id)
        self.programs = Programs(db, config.owner_telegram_id)
        self.training = Training(db)

    async def send(self, message, reply):
        if isinstance(reply, str):
            reply = Reply(reply)
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=token) for label, token in row] for row in reply.buttons]) if reply.buttons else None
        # Несколько спортсменов могут превысить лимит одного Telegram-сообщения.
        text = reply.text
        while len(text) > 3800:
            cut = text.rfind("\n", 0, 3800)
            cut = cut if cut > 0 else 3800
            await message.answer(text[:cut])
            text = text[cut:].lstrip("\n")
        await message.answer(text, reply_markup=markup)

    async def message(self, message: Message) -> None:
        # Анонимные администраторы/sender_chat не являются Telegram identity спортсмена.
        if message.from_user is None or message.from_user.is_bot or message.sender_chat:
            return
        chat_id, user_id = message.chat.id, message.from_user.id
        command, arg = command_parts(message.text or message.caption or "")
        try:
            head = (message.text or message.caption or "").strip().split(maxsplit=1)
            if head and head[0].startswith("/") and "@" in head[0]:
                target = head[0].split("@", 1)[1].lower()
                me = await message.bot.me()
                if target != (me.username or "").lower():
                    return
            if command == "/setup_group":
                reply = self.bindings.setup(chat_id, user_id, message.chat.type)
            elif command == "/bind":
                if not arg or len(arg.split()) != 1:
                    raise BotError("Используйте /bind <athlete_key>.")
                reply = self.bindings.bind(chat_id, user_id, arg, message.from_user.username, message.from_user.first_name)
            elif command == "/unbind":
                reply = self.bindings.unbind(chat_id, user_id)
            elif command == "/admin_unbind":
                if not arg or len(arg.split()) != 1:
                    raise BotError("Используйте /admin_unbind <athlete_key>.")
                reply = self.bindings.unbind(chat_id, user_id, arg)
            elif command == "/bindings":
                reply = self.bindings.inspect(chat_id, user_id)
            elif command == "/whoami":
                reply = self.bindings.whoami(chat_id, user_id)
            elif command == "/import_program":
                self.programs.authorize(chat_id, user_id)
                if message.document is None or not message.document.file_size or message.document.file_size > MAX_IMPORT_BYTES:
                    raise BotError("Прикрепите YAML до 128 КиБ с подписью /import_program.")
                buffer = LimitedBuffer()
                await message.bot.download(message.document, destination=buffer)
                reply = self.programs.import_yaml(chat_id, user_id, buffer.getvalue())
            elif command == "/start_train":
                reply = self.training.start_choices(chat_id, user_id)
            elif command == "/status":
                reply = self.training.status(chat_id, user_id)
            elif command in ("/next", "/choose", "/skip", "/undo", "/finish_train"):
                reply = self.training.command(chat_id, user_id, message.message_id, command)
            elif message.text and not command.startswith("/"):
                if not re.match(r"^\s*[+-]?\d+\s*[*xх×]", message.text):
                    return
                reply = self.training.save_result(chat_id, user_id, message.message_id, message.text)
            else:
                return
            await self.send(message, reply)
        except BotError as exc:
            if command == "/import_program":
                logger.info("event=program_import_failure chat_id=%s user_id=%s", chat_id, user_id)
            logger.info("event=rejected_action chat_id=%s user_id=%s reason=%s", chat_id, user_id, exc)
            await message.answer(str(exc))
        except SQLAlchemyError:
            logger.error("event=database_failure chat_id=%s user_id=%s", chat_id, user_id)
            await message.answer("Не удалось выполнить действие. Повторите позже или проверьте /status.")

    async def callback(self, callback: CallbackQuery) -> None:
        if callback.from_user.is_bot or not isinstance(callback.message, Message) or not callback.data or not callback.data.startswith("a:"):
            return
        try:
            reply = self.training.callback(callback.message.chat.id, callback.from_user.id, callback.data[2:])
            await callback.answer()
            await self.send(callback.message, reply)
        except BotError as exc:
            logger.info("event=rejected_action chat_id=%s user_id=%s reason=%s", callback.message.chat.id, callback.from_user.id, exc)
            await callback.answer(str(exc)[:200], show_alert=True)
        except SQLAlchemyError:
            logger.error("event=database_failure chat_id=%s", callback.message.chat.id)
            await callback.answer("Не удалось выполнить действие. Повторите команду.", show_alert=True)


def create_dispatcher(db, config) -> Dispatcher:
    handler = TelegramHandler(db, config)
    router = Router()
    router.message.register(handler.message)
    router.callback_query.register(handler.callback)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher
