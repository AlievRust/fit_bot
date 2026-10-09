"""Явные миграции с тем же SQLite-контрактом, что и приложение."""

import os

from alembic import context

from app.db.database import Database
from app.db.models import Base


def run() -> None:
    database = Database(os.environ.get("DATABASE_PATH", "data/gymbot.sqlite3"))
    try:
        with database.engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        database.close()


if context.is_offline_mode():
    raise RuntimeError("Миграции требуют подключения к локальному файлу SQLite.")
run()
