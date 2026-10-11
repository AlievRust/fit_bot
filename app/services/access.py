"""Общие проверки доверенных идентификаторов Telegram."""

from sqlalchemy import select

from app.db.models import Athlete, Binding, Settings


class BotError(Exception):
    """Безопасное сообщение пользователю; без сырого update и секретов."""


def require_owner(owner_id: int, user_id: int) -> None:
    """Разрешить действие только Telegram-пользователю, указанному в env."""
    if owner_id != user_id:
        raise BotError("Команда доступна только владельцу.")


def require_chat(s, chat_id: int) -> None:
    """Проверить, что команда пришла из единственной настроенной группы."""
    settings = s.get(Settings, 1)
    if settings is None or settings.allowed_chat_id != chat_id:
        raise BotError("Этот чат не настроен для тренировок.")


def bound_athlete(s, user_id: int) -> Athlete:
    """Найти активного спортсмена по привязке автора или вызвать BotError.

    Для идентификации используется числовой Telegram id: имя и username
    пользователь может менять, поэтому они не определяют права доступа.
    """
    athlete = s.scalar(select(Athlete).join(Binding).where(Binding.telegram_user_id == user_id, Athlete.active.is_(True)))
    if athlete is None:
        raise BotError("Сначала привяжите себя: /bind <athlete_key>.")
    return athlete
