"""Чтение истории и подготовка документов без изменения состояния бота."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.services.access import BotError, require_owner

LEGACY_PROGRAM_KEY = "legacy_telegram_2026_10_03_05"
# Консервативный предел облачного sendDocument: 50 MB, не 50 МиБ.
MAX_DOCUMENT_BYTES = 50_000_000


@dataclass(frozen=True)
class ExportDocument:
    """Готовый UTF-8 документ, существующий только в памяти запроса."""

    filename: str
    content: bytes


def iso_utc(value: datetime | str | None) -> str | None:
    """Явно обозначить UTC; наивные даты SQLite по контракту модели уже UTC."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def weight_kg(grams: int) -> str:
    """Получить точную десятичную строку, не проходя через двоичный float."""
    return format(Decimal(grams) / 1000, "f")


def markdown_text(value: object) -> str:
    """Не позволять именам разрушать структуру отчёта и его таблиц."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    for char in "\\`*_{}[]<>#|!":
        text = text.replace(char, "\\" + char)
    return text


class HistoryExport:
    """Проверять доступ, читать согласованный снимок и сериализовать историю.

    Здесь намеренно нет training/bindings и записывающей ORM-транзакции:
    экспорт работает даже до настройки группы и не создаёт служебных действий.
    """

    def __init__(self, db, owner_id: int):
        """Запомнить путь существующей БД; не открывать её до авторизации."""
        self.path = Path(db.engine.url.database).resolve()
        self.owner_id = owner_id

    def generate(self, user_id: int, chat_type: str, argument: str,
                 *, now: datetime | None = None) -> ExportDocument:
        """Подготовить один из трёх разрешённых вариантов экспорта владельцу."""
        require_owner(self.owner_id, user_id)
        if chat_type != "private":
            raise BotError(
                "Экспорт доступен только в личном чате с ботом. Откройте его профиль, "
                "перейдите в диалог, нажмите «Начать» и повторите команду там. "
                "Бот не может первым открыть личный диалог."
            )
        parts = argument.split()
        if parts not in (["chatgpt"], ["json"], ["json", "all"]):
            raise BotError("Используйте /export chatgpt, /export json или /export json all.")
        generated_at = now or datetime.now(timezone.utc)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        generated_at = generated_at.astimezone(timezone.utc)
        all_history = parts == ["json", "all"]
        try:
            snapshot = self._snapshot(generated_at, all_history)
        except sqlite3.Error:
            # SQL, пути и параметры соединения не должны попасть в Telegram.
            raise BotError("Не удалось прочитать историю. Повторите экспорт позже.") from None
        is_json = parts[0] == "json"
        text = json.dumps(snapshot, ensure_ascii=False, indent=2) if is_json else render_markdown(snapshot)
        content = (text + "\n").encode("utf-8")
        if len(content) > MAX_DOCUMENT_BYTES:
            raise BotError(
                "Экспорт превышает лимит документа Telegram (50 MB). "
                "Попробуйте /export json или /export chatgpt за последние 42 дня."
            )
        period = "all" if all_history else "42d"
        stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
        extension = "json" if is_json else "md"
        return ExportDocument(f"training-history-{period}-{stamp}.{extension}", content)

    def _snapshot(self, now: datetime, all_history: bool) -> dict:
        """Прочитать только разрешённые поля в одной read-only транзакции."""
        cutoff = now - timedelta(days=42)
        snapshot = {
            "schema_version": 1,
            "generated_at": iso_utc(now),
            "period": {
                "mode": "all" if all_history else "last_42_days",
                "from": None if all_history else iso_utc(cutoff),
                "to": None if all_history else iso_utc(now),
                "selection": "all_sessions" if all_history else "completed_by_finished_at",
            },
            "units": {"time": "UTC", "weight": "kg", "weight_encoding": "decimal_string"},
            "sessions": [],
        }
        # mode=ro запрещает запись на уровне SQLite. Явный BEGIN удерживает
        # единый снимок между запросами и не берёт BEGIN IMMEDIATE приложения.
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            sessions = connection.execute(
                """SELECT t.id, t.started_at, t.finished_at, t.status,
                          p.key AS program_key, p.version, d.key AS day_key, d.name AS day_name
                   FROM training_sessions t JOIN programs p ON p.id=t.program_id
                   JOIN program_days d ON d.id=t.program_day_id
                   WHERE ? OR (t.status='completed' AND t.finished_at BETWEEN ? AND ?)
                   ORDER BY t.started_at, t.id""",
                # ORM хранит UTC в едином ISO-формате с шестью знаками дроби.
                # Сравнение строк сохраняет микросекунды, в отличие от julianday.
                (all_history, cutoff.replace(tzinfo=None).isoformat(" ", timespec="microseconds"),
                 now.replace(tzinfo=None).isoformat(" ", timespec="microseconds")),
            ).fetchall()
            for session in sessions:
                snapshot["sessions"].append(self._session(connection, session))
            return snapshot
        finally:
            # Закрытие откатывает читающую транзакцию также при ошибке формата.
            connection.close()

    def _session(self, connection: sqlite3.Connection, session: sqlite3.Row) -> dict:
        """Собрать сессию по белому списку, без Telegram- и служебных полей."""
        session_id = session["id"]
        athletes = connection.execute(
            """SELECT a.id, a.key, a.display_name FROM session_participants sp
               JOIN athletes a ON a.id=sp.athlete_id WHERE sp.session_id=? ORDER BY a.key""",
            (session_id,),
        ).fetchall()
        exercises = connection.execute(
            """SELECT e.id, e.exercise_key, e.exercise_name, e."order",
                      (sk.exercise_id IS NOT NULL) AS skipped
               FROM program_exercises e JOIN training_sessions t ON t.program_day_id=e.program_day_id
               LEFT JOIN skipped_exercises sk ON sk.exercise_id=e.id AND sk.session_id=t.id
               WHERE t.id=? ORDER BY e."order", e.id""", (session_id,),
        ).fetchall()
        item = {
            "id": session_id, "started_at": iso_utc(session["started_at"]),
            "finished_at": iso_utc(session["finished_at"]), "status": session["status"],
            "program": {"key": session["program_key"], "version": session["version"]},
            "day": {"key": session["day_key"], "name": session["day_name"]},
            "athletes": [{"athlete_key": a["key"], "display_name": a["display_name"]} for a in athletes],
            "exercises": [],
        }
        for exercise in exercises:
            carry = exercise["exercise_key"] == "farmer_carry"
            entry = {
                "exercise_key": exercise["exercise_key"], "name": exercise["exercise_name"],
                "order": exercise["order"], "skipped": bool(exercise["skipped"]),
                "units": {"reps": "m" if carry else "count", "weight": "kg",
                          "weight_scope": "per_dumbbell" if carry else "external_load"},
                "athletes": [],
            }
            for athlete in athletes:
                plans = connection.execute(
                    """SELECT set_number AS planned_set_number, reps_min, reps_max, target_rir
                       FROM prescribed_sets WHERE program_exercise_id=? AND athlete_id=?
                       ORDER BY set_number""", (exercise["id"], athlete["id"]),
                ).fetchall()
                results = connection.execute(
                    """SELECT planned_set_number, reps, weight_g, subjective_rating, created_at
                       FROM set_results WHERE training_session_id=? AND program_exercise_id=?
                       AND athlete_id=? AND deleted_at IS NULL ORDER BY created_at, id""",
                    (session_id, exercise["id"], athlete["id"]),
                ).fetchall()
                facts = []
                for order, result in enumerate(results, 1):
                    number = result["planned_set_number"]
                    kind = "planned" if number is not None else (
                        "legacy_unplanned" if session["program_key"] == LEGACY_PROGRAM_KEY else "extra"
                    )
                    facts.append({
                        "order": order, "created_at": iso_utc(result["created_at"]), "type": kind,
                        "planned_set_number": number, "reps": result["reps"],
                        "weight_kg": weight_kg(result["weight_g"]),
                        "subjective_rating": result["subjective_rating"],
                    })
                entry["athletes"].append({
                    "athlete_key": athlete["key"], "display_name": athlete["display_name"],
                    "plans": [dict(plan) for plan in plans], "results": facts,
                })
            item["exercises"].append(entry)
        return item


def result_text(result: dict, units: dict) -> str:
    """Представить факт с единицами и только реально сохранённой оценкой."""
    reps_unit = "м" if units["reps"] == "m" else "повт."
    scope = " на одну гантель" if units["weight_scope"] == "per_dumbbell" else ""
    rating = {"easy": "легко", "normal": "норм", "hard": "тяжело"}.get(result["subjective_rating"])
    return (f"{result['reps']} {reps_unit} × {result['weight_kg']} кг{scope}"
            + (f"; {rating}" if rating else ""))


def render_markdown(snapshot: dict) -> str:
    """Сгруппировать план и факт без вычисления аналитики и рекомендаций."""
    period = snapshot["period"]
    lines = ["# История тренировок", "", f"Сформировано: {snapshot['generated_at']}",
             "Время: UTC. Вес: кг; десятичные значения сохранены точно.",
             f"Период: {period['from']} — {period['to']} (по завершению)." if period["mode"] != "all"
             else "Период: вся история, включая незавершённые сессии.",
             "Legacy-подход без номера плана не считается дополнительным. "
             "Исторический вес 1 кг приведён как хранится; исходный нулевой вес не восстанавливается."]
    if not snapshot["sessions"]:
        return "\n".join(lines + ["", "За выбранный период тренировок нет."])
    previous_date = None
    for session in snapshot["sessions"]:
        date = session["started_at"][:10]
        if date != previous_date:
            lines += ["", f"## {date}"]
            previous_date = date
        program, day = session["program"], session["day"]
        lines += ["", f"### Сессия {session['id']} — {session['status']}",
                  f"Начало: {session['started_at']}; завершение: {session['finished_at'] or '—'}.",
                  f"Программа: {markdown_text(program['key'])}, версия {program['version']}; "
                  f"день: {markdown_text(day['name'])} ({markdown_text(day['key'])})."]
        for athlete in session["athletes"]:
            lines += ["", f"#### {markdown_text(athlete['display_name'])} ({markdown_text(athlete['athlete_key'])})"]
            for exercise in session["exercises"]:
                own = next(a for a in exercise["athletes"] if a["athlete_key"] == athlete["athlete_key"])
                lines += ["", f"##### {exercise['order']}. {markdown_text(exercise['name'])} "
                          f"({markdown_text(exercise['exercise_key'])})",
                          "Пропущено всей группой." if exercise["skipped"] else "Пропуск не отмечен.",
                          "", "| Подход | План | Факт (порядок записи) |", "|---|---|---|"]
                numbered = {r["planned_set_number"]: r for r in own["results"] if r["type"] == "planned"}
                planned_numbers = set()
                unit = "м" if exercise["units"]["reps"] == "m" else "повт."
                for plan in own["plans"]:
                    number = plan["planned_set_number"]
                    planned_numbers.add(number)
                    reps = str(plan["reps_min"]) if plan["reps_min"] == plan["reps_max"] else f"{plan['reps_min']}–{plan['reps_max']}"
                    rir = "не задан" if plan["target_rir"] is None else str(plan["target_rir"])
                    fact = numbered.get(number)
                    actual = f"{result_text(fact, exercise['units'])} (№{fact['order']})" if fact else "—"
                    lines.append(f"| Плановый №{number} | {reps} {unit}; RIR {rir} | {actual} |")
                for result in own["results"]:
                    if result["type"] == "planned" and result["planned_set_number"] in planned_numbers:
                        continue
                    label = {"extra": "Дополнительный (extra)", "legacy_unplanned": "Исторический без номера плана"}.get(
                        result["type"], f"Плановый №{result['planned_set_number']} (план отсутствует)")
                    lines.append(f"| {label} | — | {result_text(result, exercise['units'])} (№{result['order']}) |")
                if not own["plans"] and not own["results"]:
                    lines.append("| — | План отсутствует | Результатов нет |")
    return "\n".join(lines)
