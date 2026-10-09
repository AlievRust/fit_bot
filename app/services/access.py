"""Общие проверки доверенных идентификаторов Telegram."""

from sqlalchemy import select

from app.db.models import Athlete, Binding, Settings


class BotError(Exception):
    """Безопасное сообщение пользователю; без сырого update и секретов."""


def require_owner(owner_id: int, user_id: int) -> None:
    if owner_id != user_id:
        raise BotError("Команда доступна только владельцу.")


def require_chat(s, chat_id: int) -> None:
    settings = s.get(Settings, 1)
    if settings is None or settings.allowed_chat_id != chat_id:
        raise BotError("Этот чат не настроен для тренировок.")


def bound_athlete(s, user_id: int) -> Athlete:
    athlete = s.scalar(select(Athlete).join(Binding).where(Binding.telegram_user_id == user_id, Athlete.active.is_(True)))
    if athlete is None:
        raise BotError("Сначала привяжите себя: /bind <athlete_key>.")
    return athlete
