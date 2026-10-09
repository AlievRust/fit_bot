"""Настройка группы и привязки, всегда по id автора команды."""

import logging

from sqlalchemy import select

from app.db.models import Athlete, Binding, Settings, TrainingSession, utcnow
from app.services.access import BotError, require_chat, require_owner

logger = logging.getLogger(__name__)


class Bindings:
    def __init__(self, db, owner_id: int):
        self.db = db
        self.owner_id = owner_id

    def setup(self, chat_id: int, user_id: int, chat_type: str) -> str:
        require_owner(self.owner_id, user_id)
        if chat_type not in ("group", "supergroup"):
            raise BotError("Выполните /setup_group в тренировочной группе.")
        with self.db.transaction() as s:
            settings = s.get(Settings, 1)
            if settings and settings.allowed_chat_id != chat_id and s.scalar(select(TrainingSession.id).where(TrainingSession.status == "active")):
                raise BotError("Сначала завершите активную тренировку в текущей группе.")
            if settings is None:
                settings = Settings(allowed_chat_id=chat_id)
                s.add(settings)
            settings.allowed_chat_id = chat_id
            settings.configured_at = utcnow()
        logger.info("event=setup_group chat_id=%s user_id=%s", chat_id, user_id)
        return "Группа настроена. Владелец может загрузить YAML с подписью /import_program."

    def bind(self, chat_id: int, user_id: int, key: str, username=None, first_name=None) -> str:
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            athlete = s.scalar(select(Athlete).where(Athlete.key == key, Athlete.active.is_(True)))
            if athlete is None:
                raise BotError("Неизвестный athlete_key. Сначала импортируйте программу.")
            if s.scalar(select(Binding.id).where(Binding.telegram_user_id == user_id)):
                raise BotError("Вы уже привязаны. Для смены используйте /unbind.")
            if s.scalar(select(Binding.id).where(Binding.athlete_id == athlete.id)):
                raise BotError("Этот спортсмен уже привязан к другому пользователю.")
            s.add(Binding(telegram_user_id=user_id, athlete_id=athlete.id, telegram_username=username, telegram_first_name=first_name))
            name = athlete.display_name
        logger.info("event=bind chat_id=%s user_id=%s athlete_key=%s", chat_id, user_id, key)
        return f"Вы привязаны к {name}."

    def unbind(self, chat_id: int, user_id: int, key: str | None = None) -> str:
        if key is not None:
            require_owner(self.owner_id, user_id)
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            if key is None:
                binding = s.scalar(select(Binding).where(Binding.telegram_user_id == user_id))
            else:
                binding = s.scalar(select(Binding).join(Athlete).where(Athlete.key == key))
            if binding is None:
                raise BotError("Привязка не найдена.")
            s.delete(binding)
        logger.info("event=unbind chat_id=%s user_id=%s recovery=%s", chat_id, user_id, key is not None)
        return "Привязка снята. Результаты тренировок сохранены."

    def whoami(self, chat_id: int, user_id: int) -> str:
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            athlete = s.scalar(select(Athlete).join(Binding).where(Binding.telegram_user_id == user_id))
            return f"Telegram id: {user_id}\nСпортсмен: {athlete.display_name} ({athlete.key})" if athlete else f"Telegram id: {user_id}\nВы не привязаны: /bind <athlete_key>."

    def inspect(self, chat_id: int, user_id: int) -> str:
        require_owner(self.owner_id, user_id)
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            rows = s.execute(select(Athlete.key, Binding.telegram_user_id).join(Binding).order_by(Athlete.key)).all()
            return "Привязки:\n" + ("\n".join(f"{key}: {uid}" for key, uid in rows) or "нет привязок")
