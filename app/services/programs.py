"""Атомарный импорт неизменяемой версии программы."""

import logging

from sqlalchemy import select, update

from app.db.models import Athlete, Day, Exercise, Prescription, Program
from app.parsers.program import parse_program, reps_bounds
from app.services.access import BotError, require_chat, require_owner

logger = logging.getLogger(__name__)


class Programs:
    """Проверять доступ и сохранять версии программы одной транзакцией."""

    def __init__(self, db, owner_id: int):
        """Сохранить БД и id владельца, которому разрешён импорт."""
        self.db = db
        self.owner_id = owner_id

    def authorize(self, chat_id: int, user_id: int) -> None:
        """Проверить владельца и чат до скачивания или разбора файла."""
        require_owner(self.owner_id, user_id)
        with self.db.transaction() as s:
            require_chat(s, chat_id)

    def import_yaml(self, chat_id: int, user_id: int, data: bytes) -> str:
        """Проверить YAML, создать его версию и сделать её активной.

        Существующие планы не перезаписываются. Активная тренировка сохраняет
        ссылки на прежнюю версию; ошибка записи откатывает весь импорт.
        """
        self.authorize(chat_id, user_id)
        document = parse_program(data)
        # Проверка документа завершена до начала транзакции записи.
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            info = document.program
            if s.scalar(select(Program.id).where(Program.key == info.key, Program.version == info.version)):
                raise BotError("Эта версия программы уже импортирована. Увеличьте version.")
            athletes = {}
            # Стабильный key сохраняет athlete.id, привязки и историю результатов.
            for item in document.athletes:
                athlete = s.scalar(select(Athlete).where(Athlete.key == item.key))
                if athlete is None:
                    athlete = Athlete(key=item.key, display_name=item.display_name)
                    s.add(athlete)
                    s.flush()
                athlete.display_name = item.display_name
                athletes[item.key] = athlete.id
            s.execute(update(Program).where(Program.active.is_(True)).values(active=False))
            # Деактивация старой версии и создание новой фиксируются вместе.
            program = Program(key=info.key, name=info.name, version=info.version, schema_version=document.schema_version)
            s.add(program)
            # flush получает id для внешних ключей, но ещё не делает commit.
            s.flush()
            for order, day_info in enumerate(document.days, 1):
                day = Day(program_id=program.id, key=day_info.key, name=day_info.name, order=order)
                s.add(day)
                s.flush()
                for exercise_info in day_info.exercises:
                    exercise = Exercise(program_day_id=day.id, exercise_key=exercise_info.key, exercise_name=exercise_info.name, order=exercise_info.order)
                    s.add(exercise)
                    s.flush()
                    for key, plans in exercise_info.prescriptions.items():
                        for number, plan in enumerate(plans, 1):
                            low, high = reps_bounds(plan.reps)
                            s.add(Prescription(program_exercise_id=exercise.id, athlete_id=athletes[key], set_number=number, reps_min=low, reps_max=high, target_rir=plan.rir))
        logger.info("event=program_import_success chat_id=%s user_id=%s program_key=%s version=%s", chat_id, user_id, info.key, info.version)
        return f"✓ Импортирована и активирована: {info.name}, версия {info.version}\nДни: {', '.join(d.name for d in document.days)}\nУпражнений: {sum(len(d.exercises) for d in document.days)}\nСпортсмены: {', '.join(a.key for a in document.athletes)}"
