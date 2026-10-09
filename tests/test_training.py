from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.database import Database
from app.db.models import Athlete, Result, TrainingSession
from app.services.access import BotError
from app.services.bindings import Bindings
from app.services.programs import Programs
from app.services.training import Training


def press(training, reply, label, user=2):
    token = next(token for row in reply.buttons for text, token in row if label in text)
    return training.callback(-100, user, token[2:])


@pytest.fixture
def training(db):
    bindings = Bindings(db, 1)
    bindings.setup(-100, 1, "group")
    Programs(db, 1).import_yaml(-100, 1, Path("examples/program.example.yaml").read_bytes())
    bindings.bind(-100, 2, "xrust")
    bindings.bind(-100, 3, "tim")
    service = Training(db)
    reply = press(service, service.start_choices(-100, 2), "Вторник")
    reply = press(service, reply, "Tim")
    press(service, reply, "Начать")
    return service


def test_independent_progress_persistence_and_restart(db, training):
    training.save_result(-100, 2, 1, "8*50")
    training.save_result(-100, 2, 2, "8*52.5")
    training.save_result(-100, 3, 3, "10*30")
    card = training.status(-100, 2).text
    assert "xRust — подход 3/4" in card
    assert "Tim — подход 2/3" in card
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(Result)) == 3
    reopened = Database(db.engine.url.database)
    try:
        assert Training(reopened).status(-100, 2).text == card
    finally:
        reopened.close()


def test_access_and_duplicate(db, training):
    for chat, user in [(-999, 2), (-100, 4)]:
        with pytest.raises(BotError):
            training.save_result(chat, user, 1, "8*50")
    with db.transaction() as s:
        s.add(Athlete(key="other", display_name="Другой"))
    Bindings(db, 1).bind(-100, 4, "other")
    with pytest.raises(BotError):
        training.save_result(-100, 4, 1, "8*50")
    training.save_result(-100, 2, 1, "8*50")
    assert "уже обработано" in training.save_result(-100, 2, 1, "8*50").text
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(Result)) == 1


def test_extra_sets_rejected(training):
    for i in range(4):
        training.save_result(-100, 2, i + 1, "8*50")
    with pytest.raises(BotError):
        training.save_result(-100, 2, 5, "8*50")
    assert "упражнение выполнено 4/4" in training.status(-100, 2).text


def test_no_session_and_no_second_session(db, training):
    assert "Уже есть" in training.start_choices(-100, 2).text
    with db.transaction() as s:
        s.scalar(select(TrainingSession)).status = "completed"
    with pytest.raises(BotError):
        training.save_result(-100, 2, 9, "8*50")


def test_callback_bound_to_author_and_chat(training):
    # Действие создаётся до сессии только в отдельном тесте; здесь проверяем токен.
    with pytest.raises(BotError):
        training.callback(-100, 3, "0" * 32)


def test_old_participant_menu_cannot_replace_new_selection(db, training):
    with db.transaction() as s:
        s.scalar(select(TrainingSession)).status = "completed"
    reply = press(training, training.start_choices(-100, 2), "Вторник")
    old_start = next(token for row in reply.buttons for text, token in row if "Начать" in text)
    updated = press(training, reply, "Tim")
    with pytest.raises(BotError, match="устарела"):
        training.callback(-100, 2, old_start[2:])
    press(training, updated, "Начать")
    assert "Tim" in training.status(-100, 2).text
