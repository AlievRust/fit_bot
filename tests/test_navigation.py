import pytest
from sqlalchemy import func, select

from app.db.models import Result, SkippedExercise, TrainingSession
from app.services.access import BotError
from app.services.training import Training
from tests.test_training import press, training


def test_next_confirmation_preserves_progress(training):
    training.save_result(-100, 2, 1, "8*50")
    reply = training.command(-100, 2, 10, "/next")
    assert "Не завершили" in reply.text
    assert "Жим" in training.status(-100, 2).text
    press(training, reply, "Перейти")
    assert "Приседания" in training.status(-100, 2).text
    choices = training.command(-100, 2, 11, "/choose")
    press(training, choices, "Жим")
    assert "xRust — подход 2/4" in training.status(-100, 2).text
    assert "Tim — подход 1/3" in training.status(-100, 2).text


def test_stale_and_foreign_confirmations(training):
    reply = training.command(-100, 2, 10, "/next")
    token = reply.buttons[0][0][1][2:]
    with pytest.raises(BotError):
        training.callback(-100, 3, token)
    with pytest.raises(BotError):
        training.callback(-999, 2, token)
    training.save_result(-100, 2, 1, "8*50")
    with pytest.raises(BotError, match="изменилось"):
        training.callback(-100, 2, token)


def test_undo_author_only_soft_delete_and_no_replay(db, training):
    training.save_result(-100, 2, 1, "8*50")
    training.save_result(-100, 2, 2, "8*55")
    training.save_result(-100, 3, 3, "10*30")
    training.command(-100, 2, 10, "/undo")
    with db.transaction() as s:
        rows = s.scalars(select(Result).order_by(Result.id)).all()
        assert [r.deleted_at is not None for r in rows] == [False, True, False]
    assert "уже обработано" in training.command(-100, 2, 10, "/undo").text
    assert "уже обработано" in training.save_result(-100, 2, 2, "8*55").text
    training.save_result(-100, 2, 4, "8*52.5")
    assert "подход 3/4" in training.status(-100, 2).text


def test_finish_restart_and_old_button(db, training):
    training.save_result(-100, 2, 1, "8*50")
    old = training.command(-100, 2, 10, "/next")
    finish = training.command(-100, 2, 11, "/finish_train")
    assert "active" == _session_status(db)
    # Новый экземпляр сервиса использует сохранённые кнопки и сессию.
    press(Training(db), finish, "Завершить")
    assert "completed" == _session_status(db)
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(Result)) == 1
    with pytest.raises(BotError):
        press(training, old, "Перейти")


def _session_status(db):
    with db.transaction() as s:
        return s.scalar(select(TrainingSession)).status


def test_skip_and_revisit(db, training):
    training.command(-100, 2, 10, "/skip")
    assert "Приседания" in training.status(-100, 2).text
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(SkippedExercise)) == 1
    reply = training.command(-100, 2, 11, "/choose")
    press(training, reply, "Жим")
    training.save_result(-100, 2, 1, "8*50")
    training.command(-100, 2, 12, "/skip")
    training.command(-100, 2, 13, "/skip")
    with pytest.raises(BotError, match="пропущено"):
        training.save_result(-100, 2, 2, "8*50")


def test_history_same_set_and_fallback(training):
    training.save_result(-100, 2, 1, "8*50")
    training.save_result(-100, 2, 2, "7*55")
    press(training, training.command(-100, 2, 10, "/finish_train"), "Завершить")
    reply = press(training, training.start_choices(-100, 2), "Вторник")
    press(training, reply, "Начать")
    assert "Прошлый раз: 8×50 кг" in training.status(-100, 2).text
    training.save_result(-100, 2, 3, "8*52.5")
    assert "Прошлый раз: 7×55 кг" in training.status(-100, 2).text
    training.save_result(-100, 2, 4, "8*57.5")
    assert "Прошлый раз: 7×55 кг" in training.status(-100, 2).text
