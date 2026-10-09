"""Автономная проверка поставки без Telegram и сетевого доступа."""

import os
import sqlite3
import sys
from pathlib import Path

# При запуске файла с bind mount приложение находится в рабочем каталоге образа.
sys.path.insert(0, str(Path.cwd()))

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from app.db.database import Database
from app.db.models import Result, TrainingSession
from app.services.bindings import Bindings
from app.services.programs import Programs
from app.services.training import Training


def press(service, reply, label):
    token = next(token for row in reply.buttons for text, token in row if label in text)
    return service.callback(-100, 2, token[2:])


def main():
    assert os.getuid() == 10001
    os.environ.setdefault("DATABASE_PATH", "/tmp/smoke.sqlite3")
    command.upgrade(Config("alembic.ini"), "head")
    command.upgrade(Config("alembic.ini"), "head")
    db = Database(os.environ["DATABASE_PATH"])
    bindings = Bindings(db, 1)
    if "--resume" in sys.argv:
        assert "xrust" in bindings.whoami(-100, 2)
        training = Training(db)
        assert "Приседания" in training.status(-100, 2).text
        press(training, training.command(-100, 2, 4, "/finish_train"), "Завершить")
        with db.transaction() as s:
            assert s.scalar(select(func.count()).select_from(Result)) == 2
            assert s.scalar(select(TrainingSession)).status == "completed"
        db.close()
        print("SMOKE PASS: другой контейнер восстановил группу, привязки, активную сессию, результаты и завершил тренировку")
        return
    bindings.setup(-100, 1, "supergroup")
    Programs(db, 1).import_yaml(-100, 1, Path("/examples/program.example.yaml").read_bytes())
    bindings.bind(-100, 2, "xrust")
    bindings.bind(-100, 3, "tim")
    training = Training(db)
    reply = press(training, training.start_choices(-100, 2), "Вторник")
    reply = press(training, reply, "Tim")
    press(training, reply, "Начать")
    training.save_result(-100, 2, 1, "8*50")
    training.save_result(-100, 3, 2, "10*30")
    press(training, training.command(-100, 2, 3, "/next"), "Перейти")
    db.close()
    db = Database(os.environ["DATABASE_PATH"])
    training = Training(db)
    assert "Приседания" in training.status(-100, 2).text
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(Result)) == 2
        assert s.scalar(select(TrainingSession)).status == "active"
    db.close()
    with sqlite3.connect(os.environ["DATABASE_PATH"]) as source, sqlite3.connect("/tmp/backup.sqlite3") as target:
        source.backup(target)
        assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert target.execute("SELECT count(*) FROM set_results").fetchone()[0] == 2
    print("SMOKE PASS: uid, миграции, импорт, привязки, подходы, навигация, восстановление, backup")


if __name__ == "__main__":
    main()
