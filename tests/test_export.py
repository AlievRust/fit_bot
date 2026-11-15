"""Контракт экспорта: содержимое, права, доставка и неизменность SQLite."""

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import SendDocument
from aiogram.types import Chat, Message, User
from sqlalchemy import select

from app.config import Config
from app.db.models import (
    Athlete, Day, Exercise, Participant, Program, Result, SkippedExercise, TrainingSession,
)
from app.handlers.telegram import TelegramHandler
from app.services.access import BotError
from app.services.export import HistoryExport, LEGACY_PROGRAM_KEY
from tests.test_training import training

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def naive(value):
    """Подготовить UTC для записи через существующие ORM-модели."""
    return value.replace(tzinfo=None)


@pytest.fixture
def history(db, training):
    """Плановые/extra, отмена, пропуск и legacy без плана в одной БД."""
    for number in range(1, 5):
        training.save_result(-100, 2, number, "50*8")
    training.save_result(-100, 2, 5, "32.125*10 тяжело")
    training.save_result(-100, 3, 6, "30*10")
    training.command(-100, 3, 7, "/undo")
    training.save_result(-100, 3, 8, "1*10")
    with db.transaction() as s:
        current = s.scalar(select(TrainingSession))
        current.started_at = naive(NOW - timedelta(days=1, hours=1))
        current.finished_at = naive(NOW - timedelta(days=1))
        current.status = "completed"
        # Одинаковое время проверяет дополнительную сортировку по id.
        for result in s.scalars(select(Result)):
            result.created_at = naive(NOW - timedelta(days=1, minutes=30))
        exercise = s.scalar(select(Exercise).where(Exercise.order == 2))
        s.add(SkippedExercise(session_id=current.id, exercise_id=exercise.id))
        athlete = s.scalar(select(Athlete).where(Athlete.key == "xrust"))
        athlete.display_name = "Рустам | *спорт* 🏋️"
        legacy = Program(key=LEGACY_PROGRAM_KEY, name="История", version=1, active=False)
        s.add(legacy)
        s.flush()
        day = Day(program_id=legacy.id, key="legacy_day", name="Историческая тренировка", order=1)
        s.add(day)
        s.flush()
        carry = Exercise(program_day_id=day.id, exercise_key="farmer_carry", exercise_name="Farmer carry", order=1)
        s.add(carry)
        s.flush()
        old = TrainingSession(
            chat_id=0, program_id=legacy.id, program_day_id=day.id, status="completed",
            current_exercise_order=1, started_by_athlete_id=athlete.id,
            started_at=naive(NOW - timedelta(days=60, hours=1)), finished_at=naive(NOW - timedelta(days=60)),
        )
        s.add(old)
        s.flush()
        s.add(Participant(session_id=old.id, athlete_id=athlete.id))
        s.add(Result(
            training_session_id=old.id, program_exercise_id=carry.id, athlete_id=athlete.id,
            planned_set_number=None, reps=40, weight_g=32125, subjective_rating=None,
            telegram_chat_id=0, telegram_message_id=None, created_at=old.started_at,
        ))
    return HistoryExport(db, 1)


def payload(service, argument="json"):
    """Разобрать реальный документ с фиксированным временем формирования."""
    document = service.generate(1, "private", argument, now=NOW)
    return json.loads(document.content)


def own(exercise, athlete_key="xrust"):
    return next(a for a in exercise["athletes"] if a["athlete_key"] == athlete_key)


def test_json_contract_and_deleted_results(history):
    data = payload(history)
    assert data["schema_version"] == 1
    assert data["generated_at"] == "2026-10-22T12:00:00Z"
    assert data["period"] == {
        "mode": "last_42_days", "from": "2026-09-10T12:00:00Z",
        "to": "2026-10-22T12:00:00Z", "selection": "completed_by_finished_at",
    }
    assert data["units"]["weight_encoding"] == "decimal_string"
    assert len(data["sessions"]) == 1
    session = data["sessions"][0]
    assert session["status"] == "completed"
    assert session["program"] == {"key": "strength_2026_10", "version": 1}
    assert session["day"] == {"key": "tuesday", "name": "Вторник"}
    assert [e["order"] for e in session["exercises"]] == [1, 2]
    bench, squat = session["exercises"]
    assert not bench["skipped"] and squat["skipped"]
    athlete = own(bench)
    assert athlete["display_name"] == "Рустам | *спорт* 🏋️"
    assert athlete["plans"][1] == {"planned_set_number": 2, "reps_min": 6, "reps_max": 8, "target_rir": 3}
    assert [r["type"] for r in athlete["results"]] == ["planned"] * 4 + ["extra"]
    assert [r["order"] for r in athlete["results"]] == [1, 2, 3, 4, 5]
    assert [r["planned_set_number"] for r in athlete["results"]] == [1, 2, 3, 4, None]
    assert athlete["results"][-1]["weight_kg"] == "32.125"
    assert athlete["results"][-1]["subjective_rating"] == "hard"
    # Отменённые 30 кг не попали в историю; технический 1 кг остаётся 1 кг.
    assert len(own(bench, "tim")["results"]) == 1
    assert own(bench, "tim")["results"][0]["weight_kg"] == "1"
    encoded = json.dumps(data)
    for secret in ("telegram", "chat_id", "user_id", "token", "binding", "revision", "deleted_at", "message_id"):
        assert secret not in encoded.lower()
    assert all("actual_rir" not in r and "comment" not in r for r in athlete["results"])


def test_all_includes_legacy_and_incomplete_sessions(db, history):
    with db.transaction() as s:
        current = s.scalar(select(TrainingSession).where(TrainingSession.chat_id == -100))
        current.status = "active"
        current.finished_at = None
    data = payload(history, "json all")
    assert data["period"] == {"mode": "all", "from": None, "to": None, "selection": "all_sessions"}
    assert [s["status"] for s in data["sessions"]] == ["completed", "active"]
    legacy = data["sessions"][0]
    assert legacy["program"]["key"] == LEGACY_PROGRAM_KEY
    carry = legacy["exercises"][0]
    assert carry["units"] == {"reps": "m", "weight": "kg", "weight_scope": "per_dumbbell"}
    result = own(carry)["results"][0]
    assert result["type"] == "legacy_unplanned" and result["planned_set_number"] is None
    assert result["reps"] == 40 and result["weight_kg"] == "32.125"
    assert result["subjective_rating"] is None and own(carry)["plans"] == []
    assert data["sessions"][1]["finished_at"] is None
    assert payload(history)["sessions"] == []


@pytest.mark.parametrize("status,offset,included", [
    ("completed", timedelta(days=-42), True),
    ("completed", timedelta(days=-42, seconds=-1), False),
    ("completed", timedelta(days=-42, microseconds=-1), False),
    ("completed", timedelta(), True),
    ("completed", timedelta(seconds=1), False),
    ("completed", timedelta(microseconds=1), False),
    ("active", timedelta(days=-1), False),
    ("aborted", timedelta(days=-1), False),
])
def test_period_boundaries_and_status(db, history, status, offset, included):
    with db.transaction() as s:
        current = s.scalar(select(TrainingSession).where(TrainingSession.chat_id == -100))
        current.status = status
        current.finished_at = naive(NOW + offset)
        # Отбор идёт по завершению, даже если тренировка началась до периода.
        current.started_at = naive(NOW - timedelta(days=43))
    assert bool(payload(history)["sessions"]) is included
    assert len(payload(history, "json all")["sessions"]) == 2
    markdown = history.generate(1, "private", "chatgpt", now=NOW).content.decode()
    assert ("За выбранный период тренировок нет." not in markdown) is included


def test_markdown_plan_fact_unicode_and_units(db, history):
    report = history.generate(1, "private", "chatgpt", now=NOW)
    assert report.filename == "training-history-42d-20261022T120000Z.md"
    text = report.content.decode("utf-8")
    assert "## 2026-10-21" in text
    assert r"Рустам \| \*спорт\* 🏋️" in text
    assert "| Плановый №2 | 6–8 повт.; RIR 3 | 50 кг × 8 повт. (№2) |" in text
    assert "Дополнительный (extra) | — | 32.125 кг × 10 повт.; тяжело (№5)" in text
    assert "30 кг × 10 повт." not in text
    assert "Пропущено всей группой." in text
    assert "RIR не задан" in text
    # Legacy в пределах периода также экспортируется обычной командой.
    with db.transaction() as s:
        old = s.scalar(select(TrainingSession).where(TrainingSession.chat_id == 0))
        old.finished_at = naive(NOW - timedelta(days=2))
    text = history.generate(1, "private", "chatgpt", now=NOW).content.decode()
    assert "Исторический без номера плана" in text
    assert "32.125 кг на одну гантель × 40 м" in text
    assert len(payload(history)["sessions"]) == 2


@pytest.mark.parametrize("argument", ["json", "json all", "chatgpt"])
def test_empty_history_without_setup_or_binding(db, argument):
    service = HistoryExport(db, 1)
    document = service.generate(1, "private", argument, now=NOW)
    if argument.startswith("json"):
        assert json.loads(document.content)["sessions"] == []
    else:
        assert "тренировок нет" in document.content.decode()


def test_export_never_changes_database(db, history, monkeypatch):
    # Долгоживущий наблюдатель обнаруживает commit другого соединения.
    observer = sqlite3.connect(db.engine.url.database)
    try:
        before = list(observer.iterdump())
        version = observer.execute("PRAGMA data_version").fetchone()[0]
        original_connect = sqlite3.connect
        traced = []

        def checked_connect(*args, **kwargs):
            assert "mode=ro" in args[0] and kwargs["uri"] is True
            connection = original_connect(*args, **kwargs)
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                connection.execute("DELETE FROM training_sessions")
            connection.rollback()
            connection.set_trace_callback(traced.append)
            return connection

        monkeypatch.setattr("app.services.export.sqlite3.connect", checked_connect)
        for command in ("json", "json all", "chatgpt"):
            history.generate(1, "private", command, now=NOW)
        assert list(observer.iterdump()) == before
        assert observer.execute("PRAGMA data_version").fetchone()[0] == version
        assert all(not query.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "COMMIT")) for query in traced)
        assert "PRAGMA query_only=ON" in traced and "BEGIN" in traced
    finally:
        observer.close()


@pytest.mark.parametrize("user,chat_type,argument,reason", [
    (2, "private", "json", "только владельцу"),
    (2, "supergroup", "json all", "только владельцу"),
    (1, "group", "json", "личном чате"),
    (1, "supergroup", "chatgpt", "личном чате"),
    (1, "channel", "json", "личном чате"),
    (1, "private", "", "Используйте"),
    (1, "private", "chatgpt all", "Используйте"),
    (1, "private", "json all extra", "Используйте"),
])
def test_reject_before_database_read(db, monkeypatch, user, chat_type, argument, reason):
    def unexpected_read(*args):
        pytest.fail("Неавторизованная или неверная команда не должна читать БД")
    service = HistoryExport(db, 1)
    monkeypatch.setattr(service, "_snapshot", unexpected_read)
    with pytest.raises(BotError, match=reason):
        service.generate(user, chat_type, argument)


def test_size_limit_and_read_failure(db, history, monkeypatch):
    document = history.generate(1, "private", "json", now=NOW)
    monkeypatch.setattr("app.services.export.MAX_DOCUMENT_BYTES", len(document.content))
    assert history.generate(1, "private", "json", now=NOW).content == document.content
    monkeypatch.setattr("app.services.export.MAX_DOCUMENT_BYTES", len(document.content) - 1)
    with pytest.raises(BotError, match="лимит документа"):
        history.generate(1, "private", "json", now=NOW)
    service = HistoryExport(db, 1)
    service.path = service.path.with_name("not-existing.sqlite3")
    with pytest.raises(BotError, match="Не удалось прочитать"):
        service.generate(1, "private", "json")
    assert not service.path.exists()


def message(user=1, chat_type="private", text="/export json"):
    return Message(message_id=1, date=0, chat=Chat(id=user if chat_type == "private" else -999, type=chat_type),
                   from_user=User(id=user, is_bot=False, first_name="Владелец"), text=text)


@pytest.mark.parametrize("argument,extension", [("json", ".json"), ("json all", ".json"), ("chatgpt", ".md")])
def test_telegram_sends_document_without_setup(db, monkeypatch, argument, extension):
    handler = TelegramHandler(db, Config(bot_token="123:secret", owner_telegram_id=1))
    document, answer = AsyncMock(), AsyncMock()
    monkeypatch.setattr(Message, "answer_document", document)
    monkeypatch.setattr(Message, "answer", answer)
    asyncio.run(handler.message(message(text="/export " + argument)))
    answer.assert_not_called()
    document.assert_awaited_once()
    file = document.call_args.args[0]
    assert file.filename.endswith(extension)
    assert file.data.decode("utf-8")


@pytest.mark.parametrize("user,chat_type", [(2, "private"), (1, "supergroup"), (2, "supergroup")])
def test_telegram_never_publishes_history(db, monkeypatch, user, chat_type):
    handler = TelegramHandler(db, Config(bot_token="123:secret", owner_telegram_id=1))
    document, answer = AsyncMock(), AsyncMock()
    monkeypatch.setattr(Message, "answer_document", document)
    monkeypatch.setattr(Message, "answer", answer)
    asyncio.run(handler.message(message(user=user, chat_type=chat_type)))
    document.assert_not_called()
    assert "История тренировок" not in answer.call_args.args[0]
    assert ("«Начать»" if user == 1 else "только владельцу") in answer.call_args.args[0]


@pytest.mark.parametrize("error_type", [TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError])
@pytest.mark.parametrize("notification_fails", [False, True])
def test_telegram_delivery_failure(db, monkeypatch, error_type, notification_fails):
    handler = TelegramHandler(db, Config(bot_token="123:secret", owner_telegram_id=1))
    error = error_type(method=SendDocument(chat_id=1, document="dummy"), message="Ошибка доставки")
    document = AsyncMock(side_effect=error)
    answer = AsyncMock(side_effect=error if notification_fails else None)
    monkeypatch.setattr(Message, "answer_document", document)
    monkeypatch.setattr(Message, "answer", answer)
    asyncio.run(handler.message(message()))
    document.assert_awaited_once()
    assert "Не удалось отправить файл экспорта" in answer.call_args.args[0]
