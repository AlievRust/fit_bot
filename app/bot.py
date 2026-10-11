"""Один процесс long polling с последовательной обработкой обновлений."""

import logging

from aiogram import Bot

from app.config import Config
from app.db.database import Database
from app.handlers.telegram import create_dispatcher

logger = logging.getLogger(__name__)


async def run(config: Config) -> None:
    """Обрабатывать Telegram-обновления до остановки и освободить ресурсы.

    Состояние тренировки хранится в БД, поэтому новый процесс продолжает его
    с сохранённого упражнения. Миграции выполняются отдельно, до запуска бота.
    """
    db = Database(config.database_path)
    bot = Bot(config.bot_token.get_secret_value())
    dispatcher = create_dispatcher(db, config)
    logger.info("event=startup")
    try:
        logger.info("event=polling_start")
        # Последовательная обработка не даёт двум обновлениям одновременно
        # менять общий указатель упражнения; транзакции дополнительно защищают БД.
        await dispatcher.start_polling(bot, handle_as_tasks=False, allowed_updates=["message", "callback_query"])
    finally:
        # finally выполняется также при ошибке polling и штатной остановке.
        await bot.session.close()
        db.close()
        logger.info("event=polling_stop")
        logger.info("event=shutdown")
