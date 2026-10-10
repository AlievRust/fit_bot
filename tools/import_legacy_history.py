#!/usr/bin/env python3
"""Одноразовый безопасный импорт legacy-истории тренировок в Arnie Fit.

Скрипт не меняет схему БД и не переключает активную программу.
Он создаёт отдельную неактивную legacy-программу, две завершённые сессии
и set_results с planned_set_number=NULL.

Запуск из корня репозитория локально:
    python tools/import_legacy_history.py \
        --input tools/legacy_history_2026_10.yaml \
        --db data/gymbot.sqlite3 \
        --dry-run

В Docker (Dockerfile не копирует tools/, поэтому каталог подключается read-only):
    docker compose run --rm --no-deps -T -v ./tools:/tools:ro bot \
        python /tools/import_legacy_history.py \
        --input /tools/legacy_history_2026_10.yaml \
        --db /app/data/gymbot.sqlite3 \
        --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# При запуске из /tools внутри контейнера /app не всегда попадает первым в sys.path.
APP_ROOT = Path("/app")
if APP_ROOT.exists() and str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.db.database import Database  # noqa: E402
from app.db.models import (  # noqa: E402
    Athlete,
    Day,
    Exercise,
    Participant,
    Program,
    Result,
    TrainingSession,
)


class ImportErrorSafe(RuntimeError):
    """Ожидаемая ошибка preflight/валидации без traceback для оператора."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Arnie legacy Telegram history")
    parser.add_argument("--input", required=True, type=Path, help="YAML с нормализованной legacy-историей")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("DATABASE_PATH", "data/gymbot.sqlite3")),
        help="Путь к существующей SQLite БД Arnie",
    )
    parser.add_argument("--dry-run", action="store_true", help="Проверить и собрать импорт, затем ROLLBACK")
    return parser.parse_args()


def load_document(path: Path) -> dict:
    if not path.is_file():
        raise ImportErrorSafe(f"Input file not found: {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ImportErrorSafe(f"Cannot read YAML {path}: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ImportErrorSafe("Expected schema_version: 1")
    if not isinstance(document.get("import"), dict) or not isinstance(document.get("sessions"), list):
        raise ImportErrorSafe("YAML must contain import: mapping and sessions: list")
    return document


def parse_dt(date_text: str, time_text: str) -> datetime:
    try:
        return datetime.fromisoformat(f"{date_text}T{time_text}:00")
    except ValueError as exc:
        raise ImportErrorSafe(f"Invalid date/time: {date_text} {time_text}") from exc


def weight_to_grams(value) -> int:
    try:
        kg = Decimal(str(value))
        grams = kg * 1000
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ImportErrorSafe(f"Invalid weight_kg: {value!r}") from exc
    if not kg.is_finite() or kg <= 0 or kg > 2000:
        raise ImportErrorSafe(f"weight_kg out of current Arnie range: {value!r}")
    if grams != grams.to_integral_value():
        raise ImportErrorSafe(f"weight_kg must be exact to 1 gram: {value!r}")
    return int(grams)


def expected_result_count(document: dict) -> int:
    total = 0
    for session in document["sessions"]:
        for exercise in session.get("exercises", []):
            for sets in exercise.get("results", {}).values():
                total += len(sets)
    return total


def validate_document(document: dict) -> None:
    spec = document["import"]
    required_import = {"key", "name", "version", "expected_active_program", "synthetic_chat_id"}
    missing = required_import - set(spec)
    if missing:
        raise ImportErrorSafe(f"Missing import fields: {sorted(missing)}")

    seen_session_keys: set[str] = set()
    for session in document["sessions"]:
        key = session.get("key")
        if not key or key in seen_session_keys:
            raise ImportErrorSafe(f"Duplicate or empty session key: {key!r}")
        seen_session_keys.add(key)
        participants = set(session.get("participants", []))
        if not participants:
            raise ImportErrorSafe(f"Session {key}: participants must not be empty")
        if session.get("started_by") not in participants:
            raise ImportErrorSafe(f"Session {key}: started_by must be a participant")
        started = parse_dt(session["date"], session["started_at"])
        finished = parse_dt(session["date"], session["finished_at"])
        if finished < started:
            raise ImportErrorSafe(f"Session {key}: finished_at before started_at")

        seen_orders: set[int] = set()
        seen_exercise_keys: set[str] = set()
        for exercise in session.get("exercises", []):
            ex_key = exercise.get("key")
            order = exercise.get("order")
            if not ex_key or ex_key in seen_exercise_keys:
                raise ImportErrorSafe(f"Session {key}: duplicate or empty exercise key {ex_key!r}")
            if not isinstance(order, int) or order <= 0 or order in seen_orders:
                raise ImportErrorSafe(f"Session {key}: invalid/duplicate exercise order {order!r}")
            seen_exercise_keys.add(ex_key)
            seen_orders.add(order)
            results = exercise.get("results")
            if not isinstance(results, dict) or not results:
                raise ImportErrorSafe(f"Session {key}/{ex_key}: results must be a non-empty mapping")
            for athlete_key, sets in results.items():
                if athlete_key not in participants:
                    raise ImportErrorSafe(f"Session {key}/{ex_key}: {athlete_key} not in participants")
                if not isinstance(sets, list) or not sets:
                    raise ImportErrorSafe(f"Session {key}/{ex_key}/{athlete_key}: empty sets")
                for item in sets:
                    reps = item.get("reps")
                    if not isinstance(reps, int) or not 1 <= reps <= 1000:
                        raise ImportErrorSafe(f"Session {key}/{ex_key}: reps out of range: {reps!r}")
                    weight_to_grams(item.get("weight_kg"))
                    at = parse_dt(session["date"], item["at"])
                    if not started <= at <= finished:
                        raise ImportErrorSafe(
                            f"Session {key}/{ex_key}: result time {at.time()} outside session interval"
                        )


def get_active_program(s: Session) -> Program:
    active = s.scalars(select(Program).where(Program.active.is_(True))).all()
    if len(active) != 1:
        raise ImportErrorSafe(f"Expected exactly one active program, found {len(active)}")
    return active[0]


def verify_expected_active(s: Session, document: dict) -> Program:
    expected = document["import"]["expected_active_program"]
    active = get_active_program(s)
    if active.key != expected.get("key") or active.version != expected.get("version"):
        raise ImportErrorSafe(
            "Active program mismatch: "
            f"DB={active.key!r} v{active.version}, "
            f"expected={expected.get('key')!r} v{expected.get('version')}"
        )
    return active


def legacy_counts(s: Session, program_id: int) -> tuple[int, int]:
    sessions = s.scalar(
        select(func.count(TrainingSession.id)).where(TrainingSession.program_id == program_id)
    ) or 0
    results = s.scalar(
        select(func.count(Result.id))
        .join(TrainingSession, Result.training_session_id == TrainingSession.id)
        .where(TrainingSession.program_id == program_id)
    ) or 0
    return sessions, results


def flatten_events(session_doc: dict, exercise_ids: dict[str, int], athlete_ids: dict[str, int]) -> list[dict]:
    events = []
    date_text = session_doc["date"]
    for exercise in session_doc["exercises"]:
        for athlete_key, sets in exercise["results"].items():
            for local_index, item in enumerate(sets):
                events.append(
                    {
                        "created_at": parse_dt(date_text, item["at"]),
                        "exercise_order": exercise["order"],
                        "local_index": local_index,
                        "program_exercise_id": exercise_ids[exercise["key"]],
                        "athlete_id": athlete_ids[athlete_key],
                        "reps": item["reps"],
                        "weight_g": weight_to_grams(item["weight_kg"]),
                    }
                )
    events.sort(key=lambda e: (e["created_at"], e["exercise_order"], e["athlete_id"], e["local_index"]))
    return events


def import_history(s: Session, document: dict) -> tuple[int, int, int, bool]:
    spec = document["import"]
    active_before = verify_expected_active(s, document)

    existing = s.scalar(
        select(Program).where(Program.key == spec["key"], Program.version == spec["version"])
    )
    expected_sessions = len(document["sessions"])
    expected_results = expected_result_count(document)
    if existing is not None:
        sessions, results = legacy_counts(s, existing.id)
        if existing.active or sessions != expected_sessions or results != expected_results:
            raise ImportErrorSafe(
                "Legacy program already exists but is incomplete/inconsistent: "
                f"active={existing.active}, sessions={sessions}/{expected_sessions}, "
                f"results={results}/{expected_results}"
            )
        return existing.id, sessions, results, False

    if spec.get("require_no_existing_training_sessions", False):
        existing_sessions = s.scalar(select(func.count(TrainingSession.id))) or 0
        if existing_sessions != 0:
            raise ImportErrorSafe(
                f"Preflight requires zero existing training sessions, found {existing_sessions}. "
                "Refusing import because legacy IDs must precede future real sessions."
            )

    athlete_keys = {
        key
        for session_doc in document["sessions"]
        for key in session_doc["participants"]
    }
    athletes = s.scalars(select(Athlete).where(Athlete.key.in_(sorted(athlete_keys)))).all()
    athlete_ids = {athlete.key: athlete.id for athlete in athletes}
    missing_athletes = sorted(athlete_keys - set(athlete_ids))
    if missing_athletes:
        raise ImportErrorSafe(
            "Athletes are missing from DB; import the active program first: " + ", ".join(missing_athletes)
        )

    legacy_program = Program(
        key=spec["key"],
        name=spec["name"],
        version=int(spec["version"]),
        schema_version=1,
        active=False,
    )
    s.add(legacy_program)
    s.flush()

    synthetic_chat_id = int(spec["synthetic_chat_id"])
    inserted_results = 0

    for day_order, session_doc in enumerate(document["sessions"], 1):
        day = Day(
            program_id=legacy_program.id,
            key=session_doc["key"],
            name=session_doc["name"],
            order=day_order,
        )
        s.add(day)
        s.flush()

        exercise_ids: dict[str, int] = {}
        for exercise_doc in sorted(session_doc["exercises"], key=lambda item: item["order"]):
            exercise = Exercise(
                program_day_id=day.id,
                exercise_key=exercise_doc["key"],
                exercise_name=exercise_doc["name"],
                order=exercise_doc["order"],
            )
            s.add(exercise)
            s.flush()
            exercise_ids[exercise_doc["key"]] = exercise.id

        started_at = parse_dt(session_doc["date"], session_doc["started_at"])
        finished_at = parse_dt(session_doc["date"], session_doc["finished_at"])
        training = TrainingSession(
            chat_id=synthetic_chat_id,
            program_id=legacy_program.id,
            program_day_id=day.id,
            status="completed",
            current_exercise_order=1,
            revision=0,
            started_at=started_at,
            finished_at=finished_at,
            started_by_athlete_id=athlete_ids[session_doc["started_by"]],
        )
        s.add(training)
        s.flush()

        for athlete_key in session_doc["participants"]:
            s.add(Participant(session_id=training.id, athlete_id=athlete_ids[athlete_key]))

        for event in flatten_events(session_doc, exercise_ids, athlete_ids):
            s.add(
                Result(
                    training_session_id=training.id,
                    program_exercise_id=event["program_exercise_id"],
                    athlete_id=event["athlete_id"],
                    planned_set_number=None,
                    reps=event["reps"],
                    weight_g=event["weight_g"],
                    subjective_rating=None,
                    telegram_chat_id=synthetic_chat_id,
                    telegram_message_id=None,
                    created_at=event["created_at"],
                    deleted_at=None,
                )
            )
            inserted_results += 1

    s.flush()

    # Главный инвариант: legacy-import никогда не должен трогать активную программу.
    active_after = get_active_program(s)
    if active_after.id != active_before.id:
        raise ImportErrorSafe("Active program changed during legacy import; rolling back")

    sessions, results = legacy_counts(s, legacy_program.id)
    if sessions != expected_sessions or results != expected_results or inserted_results != expected_results:
        raise ImportErrorSafe(
            f"Post-check mismatch: sessions={sessions}/{expected_sessions}, "
            f"results={results}/{expected_results}, inserted={inserted_results}/{expected_results}"
        )

    return legacy_program.id, sessions, results, True


def main() -> int:
    args = parse_args()
    document = load_document(args.input)
    validate_document(document)

    if not args.db.is_file():
        raise ImportErrorSafe(
            f"Database file does not exist: {args.db}. Refusing to create a new empty DB by accident."
        )

    db = Database(args.db)
    try:
        with Session(db.engine, expire_on_commit=False) as s:
            transaction = s.begin()
            try:
                program_id, sessions, results, created = import_history(s, document)
                if not created:
                    transaction.rollback()
                    print(
                        f"NO-OP: legacy history already imported: program_id={program_id}, "
                        f"sessions={sessions}, results={results}."
                    )
                elif args.dry_run:
                    transaction.rollback()
                    print(
                        f"DRY-RUN OK: would import legacy program_id={program_id}, "
                        f"sessions={sessions}, results={results}; transaction rolled back."
                    )
                else:
                    transaction.commit()
                    print(
                        f"IMPORT OK: legacy program_id={program_id}, "
                        f"sessions={sessions}, results={results}. Active program unchanged."
                    )
            except Exception:
                if transaction.is_active:
                    transaction.rollback()
                raise
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportErrorSafe as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
