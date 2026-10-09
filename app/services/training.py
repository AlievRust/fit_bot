"""Общая сессия, индивидуальный прогресс и постоянные действия кнопок."""

import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import delete, select, update

from app.db.models import (
    Action, Athlete, Binding, Day, Exercise, Participant, Prescription,
    Program, Result, TrainingSession, utcnow,
    ProcessedMessage, SkippedExercise,
)
from app.handlers.views import Reply
from app.parsers.result import parse_result
from app.services.access import BotError, bound_athlete, require_chat

logger = logging.getLogger(__name__)


def format_weight_kg(weight_g: int) -> str:
    return format(Decimal(weight_g) / 1000, "f")


class Training:
    def __init__(self, db):
        self.db = db

    def _active(self, s, chat_id):
        training = s.scalar(select(TrainingSession).where(TrainingSession.chat_id == chat_id, TrainingSession.status == "active"))
        if training is None:
            raise BotError("Нет активной тренировки. Используйте /start_train.")
        return training

    def _exercise(self, s, training):
        return s.scalar(select(Exercise).where(Exercise.program_day_id == training.program_day_id, Exercise.order == training.current_exercise_order))

    def _eligible(self, s, day_id):
        return s.scalars(select(Athlete).join(Binding).join(Prescription, Prescription.athlete_id == Athlete.id).join(Exercise, Exercise.id == Prescription.program_exercise_id).where(Exercise.program_day_id == day_id, Athlete.active.is_(True)).distinct().order_by(Athlete.id)).all()

    def _button(self, s, chat_id, user_id, label, kind, payload):
        s.execute(delete(Action).where(Action.expires_at < utcnow()))
        token = secrets.token_hex(16)
        s.add(Action(token=token, chat_id=chat_id, user_id=user_id, kind=kind, payload=payload, expires_at=utcnow() + timedelta(minutes=20)))
        return label, "a:" + token

    def _invalidate_selection(self, s, chat_id, user_id):
        # Новое меню заменяет все старые ветки выбора того же автора.
        s.execute(update(Action).where(Action.chat_id == chat_id, Action.user_id == user_id, Action.kind.in_(["day", "toggle", "begin"]), Action.used.is_(False)).values(used=True))

    def _plans_and_results(self, s, training, exercise, athlete):
        plans = s.scalars(select(Prescription).where(Prescription.program_exercise_id == exercise.id, Prescription.athlete_id == athlete.id).order_by(Prescription.set_number)).all()
        results = s.scalars(select(Result).where(Result.training_session_id == training.id, Result.program_exercise_id == exercise.id, Result.athlete_id == athlete.id, Result.deleted_at.is_(None))).all()
        numbers = {r.planned_set_number for r in results}
        next_plan = next((p for p in plans if p.set_number not in numbers), None)
        return plans, results, next_plan

    def _history(self, s, training, exercise, athlete, number):
        query = select(Result).join(TrainingSession, Result.training_session_id == TrainingSession.id).join(Exercise, Result.program_exercise_id == Exercise.id).where(
            Result.athlete_id == athlete.id, Exercise.exercise_key == exercise.exercise_key,
            TrainingSession.id < training.id, Result.deleted_at.is_(None),
        ).order_by(TrainingSession.id.desc(), Result.id.desc())
        result = s.scalar(query.where(Result.planned_set_number == number).limit(1))
        if result is None:
            result = s.scalar(query.limit(1))
        return f"{result.reps}×{format_weight_kg(result.weight_g)} кг" if result else "нет истории"

    def _hint(self, s, training, exercise, athlete):
        plans, results, plan = self._plans_and_results(s, training, exercise, athlete)
        if not plans:
            return f"{athlete.display_name} — нет плана этого упражнения"
        if plan is None:
            return f"✓ {athlete.display_name}: упражнение выполнено {len(results)}/{len(plans)}\nДалее: /next или /choose."
        reps = str(plan.reps_min) if plan.reps_min == plan.reps_max else f"{plan.reps_min}–{plan.reps_max}"
        rir = str(plan.target_rir) if plan.target_rir is not None else "не задан"
        return f"{athlete.display_name} — подход {plan.set_number}/{len(plans)}\nПлан: {reps} повторов · RIR {rir}\nПрошлый раз: {self._history(s, training, exercise, athlete, plan.set_number)}"

    def _card(self, s, training):
        program = s.get(Program, training.program_id)
        day = s.get(Day, training.program_day_id)
        exercise = self._exercise(s, training)
        exercises = s.scalars(select(Exercise).where(Exercise.program_day_id == day.id).order_by(Exercise.order)).all()
        athletes = s.scalars(select(Athlete).join(Participant).where(Participant.session_id == training.id).order_by(Athlete.id)).all()
        index = next(i for i, e in enumerate(exercises, 1) if e.id == exercise.id)
        hints = "\n\n".join(self._hint(s, training, exercise, athlete) for athlete in athletes)
        if s.get(SkippedExercise, (training.id, exercise.id)):
            hints = "Упражнение пропущено. Для возврата: /choose.\n\n" + hints
        return Reply(f"{program.name} · {day.name}\n🏋️ {exercise.exercise_name}\nУпражнение {index}/{len(exercises)}\n\n{hints}\n\nРезультат: повторы*вес, например 8*50\n/next · /choose · /skip · /undo · /finish_train")

    def start_choices(self, chat_id, user_id):
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            bound_athlete(s, user_id)
            active = s.scalar(select(TrainingSession).where(TrainingSession.chat_id == chat_id, TrainingSession.status == "active"))
            if active:
                reply = self._card(s, active)
                reply.text = "Уже есть активная тренировка. Продолжайте или выполните /finish_train.\n\n" + reply.text
                return reply
            program = s.scalar(select(Program).where(Program.active.is_(True)))
            if program is None:
                raise BotError("Владелец должен импортировать программу.")
            days = s.scalars(select(Day).where(Day.program_id == program.id).order_by(Day.order)).all()
            self._invalidate_selection(s, chat_id, user_id)
            buttons = [[self._button(s, chat_id, user_id, d.name, "day", {"day_id": d.id, "program_id": program.id})] for d in days]
            return Reply("Выберите день тренировки:", buttons)

    def _participant_choices(self, s, chat_id, user_id, payload):
        self._invalidate_selection(s, chat_id, user_id)
        eligible = self._eligible(s, payload["day_id"])
        if not eligible:
            raise BotError("В этом дне нет привязанных спортсменов с планом.")
        selected = set(payload.get("selected", [])) & {a.id for a in eligible}
        payload = {**payload, "selected": sorted(selected)}
        buttons = []
        for athlete in eligible:
            new_selected = selected ^ {athlete.id}
            buttons.append([self._button(s, chat_id, user_id, ("✓ " if athlete.id in selected else "") + athlete.display_name, "toggle", {**payload, "selected": sorted(new_selected)})])
        if selected:
            buttons.append([self._button(s, chat_id, user_id, "Начать тренировку", "begin", payload)])
        return Reply("Выберите участников, затем нажмите «Начать тренировку»:", buttons)

    def _start(self, s, chat_id, user_id, payload):
        author = bound_athlete(s, user_id)
        program = s.get(Program, payload["program_id"])
        day = s.get(Day, payload["day_id"])
        if program is None or not program.active or day is None or day.program_id != program.id:
            raise BotError("Программа изменилась. Повторите /start_train.")
        if s.scalar(select(TrainingSession.id).where(TrainingSession.chat_id == chat_id, TrainingSession.status == "active")):
            raise BotError("Уже есть активная тренировка. Используйте /status.")
        eligible = {a.id for a in self._eligible(s, day.id)}
        selected = set(payload["selected"])
        if not selected or not selected <= eligible:
            raise BotError("Привязки участников изменились. Повторите /start_train.")
        first = s.scalar(select(Exercise).where(Exercise.program_day_id == day.id).order_by(Exercise.order).limit(1))
        training = TrainingSession(chat_id=chat_id, program_id=program.id, program_day_id=day.id, current_exercise_order=first.order, started_by_athlete_id=author.id)
        s.add(training)
        s.flush()
        s.add_all(Participant(session_id=training.id, athlete_id=athlete_id) for athlete_id in selected)
        s.flush()
        logger.info("event=training_start chat_id=%s session_id=%s user_id=%s", chat_id, training.id, user_id)
        return self._card(s, training)

    def callback(self, chat_id, user_id, token):
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            bound_athlete(s, user_id)
            action = s.get(Action, token)
            if not action or action.used or action.expires_at < utcnow() or action.chat_id != chat_id or action.user_id != user_id:
                raise BotError("Кнопка устарела или предназначена другому участнику. Повторите команду.")
            action.used = True
            payload = action.payload
            if action.kind == "day":
                author = bound_athlete(s, user_id)
                payload = {**payload, "selected": [author.id]}
                return self._participant_choices(s, chat_id, user_id, payload)
            if action.kind == "toggle":
                return self._participant_choices(s, chat_id, user_id, payload)
            if action.kind == "begin":
                return self._start(s, chat_id, user_id, payload)
            return self._navigation_callback(s, chat_id, user_id, action)

    def save_result(self, chat_id, user_id, message_id, text):
        parsed = parse_result(text)
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            athlete = bound_athlete(s, user_id)
            if s.scalar(select(Result.id).where(Result.telegram_chat_id == chat_id, Result.telegram_message_id == message_id)):
                return Reply("Это сообщение уже обработано. Используйте /status.")
            training = self._active(s, chat_id)
            if s.get(Participant, (training.id, athlete.id)) is None:
                raise BotError("Вы не участник активной тренировки.")
            exercise = self._exercise(s, training)
            if s.get(SkippedExercise, (training.id, exercise.id)):
                raise BotError("Упражнение пропущено. Используйте /choose для возврата или /finish_train.")
            plans, _, plan = self._plans_and_results(s, training, exercise, athlete)
            if plan is None:
                raise BotError("Все плановые подходы выполнены или плана нет. Используйте /next или /choose.")
            weight_g = int(parsed.weight * 1000)
            result = Result(training_session_id=training.id, program_exercise_id=exercise.id, athlete_id=athlete.id, planned_set_number=plan.set_number, reps=parsed.reps, weight_g=weight_g, subjective_rating=parsed.rating, telegram_chat_id=chat_id, telegram_message_id=message_id)
            s.add(result)
            training.revision += 1
            s.flush()
            reply = Reply(f"✓ {athlete.display_name}: {parsed.reps}×{format_weight_kg(weight_g)} кг\n\n" + self._hint(s, training, exercise, athlete))
        logger.info("event=set_result_saved chat_id=%s session_id=%s athlete_id=%s message_id=%s", chat_id, training.id, athlete.id, message_id)
        return reply

    def status(self, chat_id, user_id):
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            bound_athlete(s, user_id)
            return self._card(s, self._active(s, chat_id))

    def _require_participant(self, s, training, user_id):
        athlete = bound_athlete(s, user_id)
        if s.get(Participant, (training.id, athlete.id)) is None:
            raise BotError("Управление тренировкой доступно её участникам.")
        return athlete

    def _session_button(self, s, training, user_id, label, kind, **extra):
        payload = {"session_id": training.id, "revision": training.revision, **extra}
        return self._button(s, training.chat_id, user_id, label, kind, payload)

    def _incomplete(self, s, training):
        exercise = self._exercise(s, training)
        athletes = s.scalars(select(Athlete).join(Participant).where(Participant.session_id == training.id)).all()
        return [a.display_name for a in athletes if self._plans_and_results(s, training, exercise, a)[2] is not None]

    def _move(self, s, training, user_id, target=None):
        if target is None:
            exercise = s.scalar(select(Exercise).where(Exercise.program_day_id == training.program_day_id, Exercise.order > training.current_exercise_order).order_by(Exercise.order).limit(1))
        else:
            exercise = s.scalar(select(Exercise).where(Exercise.id == target, Exercise.program_day_id == training.program_day_id))
        if exercise is None:
            return Reply("Это последнее упражнение. Для завершения: /finish_train.")
        if target is not None:
            skipped = s.get(SkippedExercise, (training.id, exercise.id))
            if skipped:
                s.delete(skipped)
        training.current_exercise_order = exercise.order
        training.revision += 1
        s.flush()
        logger.info("event=navigation chat_id=%s session_id=%s user_id=%s exercise_id=%s", training.chat_id, training.id, user_id, exercise.id)
        return self._card(s, training)

    def command(self, chat_id, user_id, message_id, command):
        with self.db.transaction() as s:
            require_chat(s, chat_id)
            training = self._active(s, chat_id)
            athlete = self._require_participant(s, training, user_id)
            if s.get(ProcessedMessage, (chat_id, message_id)):
                return Reply("Это сообщение уже обработано. Используйте /status.")
            s.add(ProcessedMessage(chat_id=chat_id, message_id=message_id))
            if command == "/next":
                incomplete = self._incomplete(s, training)
                if incomplete:
                    button = self._session_button(s, training, user_id, "Перейти, сохранив прогресс", "next")
                    return Reply("Не завершили упражнение: " + ", ".join(incomplete) + ".\nПодтвердите переход:", [[button]])
                return self._move(s, training, user_id)
            if command == "/choose":
                exercises = s.scalars(select(Exercise).where(Exercise.program_day_id == training.program_day_id).order_by(Exercise.order)).all()
                buttons = []
                for exercise in exercises:
                    skipped = s.get(SkippedExercise, (training.id, exercise.id))
                    label = exercise.exercise_name + (" (пропущено)" if skipped else "")
                    buttons.append([self._session_button(s, training, user_id, label, "choose", exercise_id=exercise.id)])
                return Reply("Выберите упражнение:", buttons)
            if command == "/skip":
                exercise = self._exercise(s, training)
                if s.get(SkippedExercise, (training.id, exercise.id)) is None:
                    s.add(SkippedExercise(session_id=training.id, exercise_id=exercise.id))
                training.revision += 1
                s.flush()
                logger.info("event=navigation_skip chat_id=%s session_id=%s user_id=%s exercise_id=%s", chat_id, training.id, user_id, exercise.id)
                reply = self._move(s, training, user_id)
                reply.text = f"Пропущено: {exercise.exercise_name}.\n\n" + reply.text
                return reply
            if command == "/undo":
                result = s.scalar(select(Result).where(Result.training_session_id == training.id, Result.athlete_id == athlete.id, Result.deleted_at.is_(None)).order_by(Result.id.desc()).limit(1))
                if result is None:
                    raise BotError("У вас нет результатов для отмены в этой тренировке.")
                result.deleted_at = utcnow()
                training.revision += 1
                s.flush()
                logger.info("event=set_result_undone chat_id=%s session_id=%s athlete_id=%s result_id=%s", chat_id, training.id, athlete.id, result.id)
                exercise = s.get(Exercise, result.program_exercise_id)
                reply = self._card(s, training)
                reply.text = f"Отменён ваш подход {result.planned_set_number}: {exercise.exercise_name}, {result.reps}×{format_weight_kg(result.weight_g)} кг.\n\n" + reply.text
                return reply
            if command == "/finish_train":
                button = self._session_button(s, training, user_id, "Завершить тренировку", "finish")
                return Reply("Завершить тренировку? Все записанные результаты сохранятся.", [[button]])
            raise BotError("Неизвестная команда тренировки.")

    def _navigation_callback(self, s, chat_id, user_id, action):
        training = self._active(s, chat_id)
        self._require_participant(s, training, user_id)
        if training.id != action.payload.get("session_id") or training.revision != action.payload.get("revision"):
            raise BotError("Состояние тренировки изменилось. Повторите команду и подтвердите заново.")
        if action.kind == "next":
            return self._move(s, training, user_id)
        if action.kind == "choose":
            return self._move(s, training, user_id, action.payload["exercise_id"])
        if action.kind == "finish":
            training.status = "completed"
            training.finished_at = utcnow()
            training.revision += 1
            logger.info("event=training_finish chat_id=%s session_id=%s user_id=%s", chat_id, training.id, user_id)
            return Reply("✓ Тренировка завершена. Все результаты сохранены. Новая тренировка: /start_train.")
        raise BotError("Неизвестная кнопка. Повторите команду.")
