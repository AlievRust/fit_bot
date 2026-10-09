import pytest
from sqlalchemy import select

from app.db.models import Athlete, Binding
from app.services.access import BotError
from app.services.bindings import Bindings


@pytest.fixture
def bindings(db):
    service = Bindings(db, 1)
    service.setup(-100, 1, "supergroup")
    with db.transaction() as s:
        s.add_all([Athlete(key="xrust", display_name="xRust"), Athlete(key="tim", display_name="Tim")])
    return service


def test_self_bind_author_unique_and_recovery(db, bindings):
    bindings.bind(-100, 2, "xrust")
    with db.transaction() as s:
        assert s.scalar(select(Binding)).telegram_user_id == 2
    assert "xrust: 2" in bindings.inspect(-100, 1)
    assert "xrust" in bindings.whoami(-100, 2)
    for user, key in [(3, "xrust"), (2, "tim"), (3, "unknown")]:
        with pytest.raises(BotError):
            bindings.bind(-100, user, key)
    bindings.unbind(-100, 1, "xrust")
    bindings.bind(-100, 3, "xrust")
    bindings.unbind(-100, 3)
    bindings.bind(-100, 3, "tim")


def test_access_boundaries(bindings):
    with pytest.raises(BotError):
        bindings.bind(-999, 2, "xrust")
    with pytest.raises(BotError):
        bindings.inspect(-100, 2)
    with pytest.raises(BotError):
        bindings.unbind(-100, 2, "xrust")
    with pytest.raises(BotError):
        bindings.setup(-100, 2, "supergroup")
    with pytest.raises(BotError):
        bindings.setup(1, 1, "private")
