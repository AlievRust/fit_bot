from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select

from app.db.models import Athlete, Program
from app.parsers.program import parse_program
from app.services.access import BotError
from app.services.bindings import Bindings
from app.services.programs import Programs

SAMPLE = Path("examples/program.example.yaml").read_bytes()


@pytest.fixture
def programs(db):
    Bindings(db, 1).setup(-100, 1, "group")
    return Programs(db, 1)


def test_atomic_import_and_duplicate(db, programs):
    assert "версия 1" in programs.import_yaml(-100, 1, SAMPLE)
    with pytest.raises(BotError):
        programs.import_yaml(-100, 1, SAMPLE)
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(Program)) == 1
        assert s.scalar(select(func.count()).select_from(Athlete)) == 2


@pytest.mark.parametrize("reps", ["8", "6-8", "1-1000"])
def test_valid_reps(reps):
    raw = yaml.safe_load(SAMPLE)
    raw["days"][0]["exercises"][0]["prescriptions"]["xrust"][0]["reps"] = reps
    assert parse_program(yaml.safe_dump(raw).encode()).schema_version == 1


@pytest.mark.parametrize("value", ["0", "8-6", "8-1001", "8x", 8, "-1"])
def test_invalid_reps_atomic(value, db, programs):
    raw = yaml.safe_load(SAMPLE)
    raw["days"][0]["exercises"][0]["prescriptions"]["xrust"][0]["reps"] = value
    with pytest.raises(BotError):
        programs.import_yaml(-100, 1, yaml.safe_dump(raw).encode())
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(Program)) == 0
        assert s.scalar(select(func.count()).select_from(Athlete)) == 0


def test_unknown_athlete_and_duplicate_yaml(programs):
    with pytest.raises(BotError):
        programs.import_yaml(-100, 1, SAMPLE.replace(b"prescriptions:\n          xrust:", b"prescriptions:\n          unknown:"))
    with pytest.raises(BotError):
        parse_program(b"schema_version: 1\nschema_version: 2")
    with pytest.raises(BotError):
        parse_program(b"a: &x [1]\nb: *x")


def test_import_owner_only(programs):
    with pytest.raises(BotError):
        programs.import_yaml(-100, 2, SAMPLE)
    with pytest.raises(BotError):
        programs.import_yaml(-999, 1, SAMPLE)
