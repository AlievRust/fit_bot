"""Точка входа long polling."""

import asyncio
import logging

from pydantic import ValidationError

from app.config import Config
from app.logging_setup import protect_logs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = Config.from_env()
    except ValidationError:
        raise SystemExit("Проверьте BOT_TOKEN, OWNER_TELEGRAM_ID и DATABASE_PATH.") from None
    from app.bot import run

    protect_logs(config.bot_token.get_secret_value())
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
