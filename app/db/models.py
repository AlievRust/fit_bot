"""Реляционная модель: планы отделены от результатов тренировки."""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index,
    Integer, JSON, String, UniqueConstraint, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Athlete(Base):
    __tablename__ = "athletes"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Binding(Base):
    __tablename__ = "telegram_bindings"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(100))
    telegram_first_name: Mapped[str | None] = mapped_column(String(100))
    bound_at: Mapped[datetime] = mapped_column(default=utcnow)


class Settings(Base):
    __tablename__ = "app_settings"
    __table_args__ = (CheckConstraint("id = 1", name="settings_singleton"),)
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    allowed_chat_id: Mapped[int] = mapped_column(BigInteger)
    configured_at: Mapped[datetime] = mapped_column(default=utcnow)


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        UniqueConstraint("key", "version", name="program_version_unique"),
        CheckConstraint("version > 0 AND schema_version = 1", name="program_versions_valid"),
        Index("one_active_program", "active", unique=True, sqlite_where=text("active = 1")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Day(Base):
    __tablename__ = "program_days"
    __table_args__ = (
        UniqueConstraint("program_id", "key"), UniqueConstraint("program_id", "order"),
        CheckConstraint('"order" > 0', name="day_order_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    order: Mapped[int] = mapped_column(Integer)


class Exercise(Base):
    __tablename__ = "program_exercises"
    __table_args__ = (
        UniqueConstraint("program_day_id", "exercise_key"),
        UniqueConstraint("program_day_id", "order"),
        CheckConstraint('"order" > 0', name="exercise_order_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    program_day_id: Mapped[int] = mapped_column(ForeignKey("program_days.id"))
    exercise_key: Mapped[str] = mapped_column(String(64))
    exercise_name: Mapped[str] = mapped_column(String(100))
    order: Mapped[int] = mapped_column(Integer)


class Prescription(Base):
    __tablename__ = "prescribed_sets"
    __table_args__ = (
        UniqueConstraint("program_exercise_id", "athlete_id", "set_number"),
        CheckConstraint("set_number > 0 AND reps_min > 0 AND reps_max >= reps_min AND reps_max <= 1000", name="prescription_positive"),
        CheckConstraint("target_rir IS NULL OR target_rir BETWEEN 0 AND 10", name="rir_valid"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    program_exercise_id: Mapped[int] = mapped_column(ForeignKey("program_exercises.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    set_number: Mapped[int] = mapped_column(Integer)
    reps_min: Mapped[int] = mapped_column(Integer)
    reps_max: Mapped[int] = mapped_column(Integer)
    target_rir: Mapped[int | None] = mapped_column(Integer)


class TrainingSession(Base):
    __tablename__ = "training_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'aborted')", name="session_status_valid"),
        Index("one_active_session_per_chat", "chat_id", unique=True, sqlite_where=text("status = 'active'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))
    program_day_id: Mapped[int] = mapped_column(ForeignKey("program_days.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")
    current_exercise_order: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_by_athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))


class Participant(Base):
    __tablename__ = "session_participants"
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), primary_key=True)


class Result(Base):
    __tablename__ = "set_results"
    __table_args__ = (
        CheckConstraint("reps BETWEEN 1 AND 1000", name="result_reps_valid"),
        CheckConstraint("typeof(weight_g) = 'integer' AND weight_g BETWEEN 1 AND 2000000", name="result_weight_g_valid"),
        CheckConstraint("subjective_rating IS NULL OR subjective_rating IN ('easy', 'normal', 'hard')", name="rating_valid"),
        UniqueConstraint("telegram_chat_id", "telegram_message_id", name="result_message_unique"),
        Index("one_live_planned_result", "training_session_id", "program_exercise_id", "athlete_id", "planned_set_number", unique=True, sqlite_where=text("deleted_at IS NULL")),
        Index("result_history", "athlete_id", "program_exercise_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    training_session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"))
    program_exercise_id: Mapped[int] = mapped_column(ForeignKey("program_exercises.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    planned_set_number: Mapped[int | None] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)
    weight_g: Mapped[int] = mapped_column(Integer)
    subjective_rating: Mapped[str | None] = mapped_column(String(16))
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class SkippedExercise(Base):
    __tablename__ = "skipped_exercises"
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("program_exercises.id"), primary_key=True)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Action(Base):
    """Одноразовая серверная кнопка, связанная с автором, чатом и версией состояния."""

    __tablename__ = "pending_actions"
    token: Mapped[str] = mapped_column(String(32), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
