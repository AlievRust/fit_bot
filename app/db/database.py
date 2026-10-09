"""Соединения SQLite и сериализация коротких транзакций."""

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import Session


class Database:
    def __init__(self, path: Path | str):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            URL.create("sqlite", database=str(path.resolve())),
            connect_args={"timeout": 10},
        )

        @event.listens_for(self.engine, "connect")
        def configure(dbapi_connection, _):
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        @event.listens_for(self.engine, "begin")
        def begin(connection):
            # Выбор номера подхода и запись происходят под одной write-блокировкой.
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    @contextmanager
    def transaction(self):
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            yield session

    def close(self) -> None:
        self.engine.dispose()
