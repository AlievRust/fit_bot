from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select

from app.db.models import Result
from tests.test_training import training


def test_concurrent_duplicate_message_records_one_set(db, training):
    barrier = Barrier(2)
    def save(_):
        barrier.wait(timeout=10)
        return training.save_result(-100, 2, 100, "8*50")
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(save, [0, 1]))
    assert sum("уже обработано" in reply.text for reply in replies) == 1
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(Result)) == 1
    assert "xRust — подход 2/4" in training.status(-100, 2).text


def test_concurrent_sets_keep_individual_numbers(db, training):
    barrier = Barrier(2)
    def save(user):
        barrier.wait(timeout=10)
        return training.save_result(-100, user, 100 + user, "8*50")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(save, [2, 3]))
    card = training.status(-100, 2).text
    assert "xRust — подход 2/4" in card
    assert "Tim — подход 2/3" in card
