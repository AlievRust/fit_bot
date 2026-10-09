from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.db.database import Database


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    database = Database(path)
    yield database
    database.close()
