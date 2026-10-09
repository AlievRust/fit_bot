"""Конфигурация из переменных окружения без раскрытия секретов."""

import os
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator


class Config(BaseModel):
    bot_token: SecretStr
    owner_telegram_id: int = Field(gt=0, le=2**63 - 1)
    database_path: Path = Path("data/gymbot.sqlite3")

    @field_validator("bot_token")
    @classmethod
    def token_present(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("BOT_TOKEN обязателен")
        return value

    @classmethod
    def from_env(cls) -> "Config":
        return cls.model_validate(
            {
                "bot_token": os.environ.get("BOT_TOKEN", ""),
                "owner_telegram_id": os.environ.get("OWNER_TELEGRAM_ID", ""),
                "database_path": os.environ.get("DATABASE_PATH", "data/gymbot.sqlite3"),
            }
        )
