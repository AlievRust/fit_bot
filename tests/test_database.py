import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.database import Database
from app.db.models import Athlete, Binding, Day, Exercise, Program, Result, TrainingSession


def test_binding_uniqueness_and_foreign_keys(db):
    with db.transaction() as s:
        a = Athlete(key="a", display_name="А")
        b = Athlete(key="b", display_name="Б")
        s.add_all([a, b])
        s.flush()
        ids = a.id, b.id
        s.add(Binding(telegram_user_id=2**40, athlete_id=a.id))
    for user, athlete in [(2**40, ids[1]), (2**40 + 1, ids[0]), (9, 999)]:
        with pytest.raises(IntegrityError), db.transaction() as s:
            s.add(Binding(telegram_user_id=user, athlete_id=athlete))


def test_migrations_repeat_and_grams_restart(db):
    command.upgrade(Config("alembic.ini"), "head")
    with db.transaction() as s:
        a = Athlete(key="a", display_name="А")
        p = Program(key="p", name="П", version=1)
        s.add_all([a, p])
        s.flush()
        day = Day(program_id=p.id, key="day", name="День", order=1)
        s.add(day)
        s.flush()
        exercise = Exercise(program_day_id=day.id, exercise_key="e", exercise_name="Упражнение", order=1)
        session = TrainingSession(chat_id=-123, program_id=p.id, program_day_id=day.id, current_exercise_order=1, started_by_athlete_id=a.id)
        s.add_all([exercise, session])
        s.flush()
        s.add(Result(training_session_id=session.id, program_exercise_id=exercise.id, athlete_id=a.id, planned_set_number=1, reps=8, weight_g=32125, telegram_chat_id=-123, telegram_message_id=1))
        session_values = dict(chat_id=-123, program_id=p.id, program_day_id=day.id, current_exercise_order=1, started_by_athlete_id=a.id)
    with pytest.raises(IntegrityError), db.transaction() as s:
        s.add(TrainingSession(**session_values))
    path = db.engine.url.database
    db.close()
    reopened = Database(path)
    try:
        with reopened.transaction() as s:
            assert s.scalar(select(Result)).weight_g == 32125
            assert s.scalar(select(TrainingSession)).status == "active"
    finally:
        reopened.close()
