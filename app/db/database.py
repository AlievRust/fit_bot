"""Соединения SQLite и сериализация коротких транзакций."""

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import Session


class Database:
    """Управлять соединениями с одним файлом SQLite и границами транзакций.

    Сервисы получают ORM Session через transaction, а не держат состояние
    тренировки в памяти. Создание схемы относится к миграциям Alembic.
    """

    def __init__(self, path: Path | str):
        """Создать движок и настроить каждое открываемое SQLite-соединение."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            URL.create("sqlite", database=str(path.resolve())),
            connect_args={"timeout": 10},
        )

        @event.listens_for(self.engine, "connect")
        def configure(dbapi_connection, _):
            """Включить внешние ключи, ожидание блокировки и журнал WAL."""
            # Отключаем неявный BEGIN драйвера: начало транзакции задаём ниже.
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            # WAL позволяет читателям работать, пока другой процесс пишет.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        @event.listens_for(self.engine, "begin")
        def begin(connection):
            """Получить блокировку записи в самом начале транзакции."""
            # Выбор номера подхода и запись происходят под одной write-блокировкой.
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    @contextmanager
    def transaction(self):
        """Выдать ORM-сессию: успех фиксируется, исключение откатывает изменения.

        flush отправляет SQL, но не завершает транзакцию. Commit происходит
        при выходе из блока with. expire_on_commit=False позволяет после этого
        читать уже загруженные поля объектов, например для записи в журнал.
        """
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            yield session

    def close(self) -> None:
        """Освободить соединения движка при остановке приложения."""
        self.engine.dispose()
