"""Интеграционные сценарии плановых и дополнительных рабочих подходов."""

import pytest
from sqlalchemy import select

from app.db.database import Database
from app.db.models import Athlete, Prescription, Result
from app.services.access import BotError
from app.services.training import Training
from tests.test_training import press, training


def complete_tim_plan(training):
    """Заполнить три плановых подхода Tim с известными id сообщений."""
    for message_id in range(100, 103):
        reply = training.save_result(-100, 3, message_id, "8*30")
    return reply


def test_extra_after_three_planned_sets(db, training):
    """Завершение плана подсказывает extra; следующая запись получает NULL."""
    completed = complete_tim_plan(training)
    assert "Tim: план выполнен 3/3" in completed.text
    assert "отправить ещё результат — запишу как дополнительный подход" in completed.text
    assert "/next — перейти дальше" in completed.text

    reply = training.save_result(-100, 3, 103, "10*20")
    assert "✓ Tim: дополнительный подход — 10×20 кг" in reply.text
    assert "план выполнен 3/3" in reply.text
    with db.transaction() as s:
        rows = s.scalars(select(Result).order_by(Result.id)).all()
        assert [r.planned_set_number for r in rows] == [1, 2, 3, None]
        assert (rows[-1].reps, rows[-1].weight_g) == (10, 20000)


def test_multiple_extras_keep_counter_and_survive_restart(db, training):
    """Каждое новое сообщение сохраняется отдельно, план остаётся 3/3."""
    complete_tim_plan(training)
    for message_id in range(103, 106):
        reply = training.save_result(-100, 3, message_id, "10*20")
        assert "план выполнен 3/3" in reply.text
    card = training.status(-100, 2).text
    assert "Tim: план выполнен 3/3" in card
    assert "xRust — подход 1/4" in card
    with db.transaction() as s:
        extras = s.scalars(select(Result).where(Result.planned_set_number.is_(None))).all()
        assert len(extras) == 3
        assert len({r.id for r in extras}) == 3
        assert {r.telegram_message_id for r in extras} == {103, 104, 105}

    reopened = Database(db.engine.url.database)
    try:
        assert Training(reopened).status(-100, 2).text == card
        with reopened.transaction() as s:
            assert len(s.scalars(select(Result).where(Result.planned_set_number.is_(None))).all()) == 3
    finally:
        reopened.close()


def test_undo_extra_is_author_only_and_allows_new_extra(db, training):
    """Мягкая отмена extra не трогает чужой подход и не допускает replay."""
    complete_tim_plan(training)
    training.save_result(-100, 3, 103, "10*20")
    training.save_result(-100, 2, 200, "8*50")

    reply = training.command(-100, 3, 900, "/undo")
    assert "Отменён ваш дополнительный подход" in reply.text
    assert "None" not in reply.text
    assert "Tim: план выполнен 3/3" in reply.text
    assert "уже обработано" in training.command(-100, 3, 900, "/undo").text
    assert "уже обработано" in training.save_result(-100, 3, 103, "10*20").text

    replacement = training.save_result(-100, 3, 104, "12*22.5")
    assert "дополнительный подход — 12×22.5 кг" in replacement.text
    with db.transaction() as s:
        rows = s.scalars(select(Result).order_by(Result.id)).all()
        assert [r.deleted_at is not None for r in rows] == [False, False, False, True, False, False]
        assert [r.planned_set_number for r in rows] == [1, 2, 3, None, 1, None]


def test_plan_undo_restores_planned_number_before_extra(db, training):
    """После отмены extra и последнего планового сначала восстанавливается план."""
    complete_tim_plan(training)
    training.save_result(-100, 3, 103, "10*20")
    training.command(-100, 3, 900, "/undo")
    reply = training.command(-100, 3, 901, "/undo")
    assert "Tim — подход 3/3" in reply.text

    planned = training.save_result(-100, 3, 104, "8*32.5")
    assert "дополнительный подход" not in planned.text.split("\n\n", 1)[0]
    training.save_result(-100, 3, 105, "10*20")
    with db.transaction() as s:
        assert s.scalars(select(Result.planned_set_number).where(Result.deleted_at.is_(None)).order_by(Result.id)).all() == [1, 2, 3, None]


@pytest.mark.parametrize("number", [1, 2, 3, 4])
def test_planned_history_has_priority_over_latest_extra(training, number):
    """Более поздний extra не заменяет историю соответствующего планового номера."""
    previous = ["8*50", "7*55", "6*60", "5*65"]
    for message_id, text in enumerate(previous, 1):
        training.save_result(-100, 2, message_id, text)
    training.save_result(-100, 2, 5, "10*20")
    press(training, training.command(-100, 2, 900, "/finish_train"), "Завершить")
    reply = press(training, training.start_choices(-100, 2), "Вторник")
    press(training, reply, "Начать")
    for index in range(number - 1):
        training.save_result(-100, 2, 100 + index, "8*52.5")

    reps, weight = previous[number - 1].split("*")
    card = training.status(-100, 2).text
    assert f"Прошлый раз: {reps}×{weight} кг" in card
    assert "Прошлый раз: 10×20 кг" not in card


def test_extra_remains_available_to_history_fallback(db, training):
    """Если номера в истории нет, fallback вправе взять последний extra."""
    complete_tim_plan(training)
    training.save_result(-100, 3, 103, "10*20")
    with db.transaction() as s:
        exercise = training._exercise(s, training._active(s, -100))
        athlete = s.scalar(select(Athlete).where(Athlete.key == "tim"))
        training_id = training._active(s, -100).id
    press(training, training.command(-100, 2, 900, "/finish_train"), "Завершить")
    reply = press(training, training.start_choices(-100, 2), "Вторник")
    press(training, reply, "Начать")
    with db.transaction() as s:
        current = training._active(s, -100)
        assert current.id > training_id
        assert training._history(s, current, exercise, athlete, 4) == "10×20 кг"


def test_extra_does_not_allow_result_without_prescription(db, training):
    """Отсутствие плана не приравнивается к его завершению."""
    with db.transaction() as s:
        athlete_id = s.scalar(select(Athlete.id).where(Athlete.key == "tim"))
        exercise = training._exercise(s, training._active(s, -100))
        plans = s.scalars(select(Prescription).where(Prescription.athlete_id == athlete_id, Prescription.program_exercise_id == exercise.id)).all()
        for plan in plans:
            s.delete(plan)
    with pytest.raises(BotError, match="Плана этого упражнения нет"):
        training.save_result(-100, 3, 103, "10*20")
    with db.transaction() as s:
        assert not s.scalars(select(Result)).all()


def test_next_after_extras_preserves_old_results(db, training):
    """После перехода новый результат относится к плану следующего упражнения."""
    complete_tim_plan(training)
    training.save_result(-100, 3, 103, "10*20")
    next_reply = training.command(-100, 3, 900, "/next")
    assert "xRust" in next_reply.text
    assert "Tim" not in next_reply.text
    press(training, next_reply, "Перейти", user=3)
    training.save_result(-100, 3, 104, "8*40")
    with db.transaction() as s:
        rows = s.scalars(select(Result).order_by(Result.id)).all()
        assert rows[-2].planned_set_number is None
        assert rows[-1].planned_set_number == 1
        assert rows[-1].program_exercise_id != rows[-2].program_exercise_id
    choices = training.command(-100, 3, 901, "/choose")
    press(training, choices, "Жим", user=3)
    assert "Tim: план выполнен 3/3" in training.status(-100, 3).text
