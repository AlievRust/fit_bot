import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.test_training import press, training


@pytest.mark.parametrize("kilograms,grams", [
    ("50", 50000), ("32.5", 32500), ("32.125", 32125),
    ("0.001", 1), ("2000", 2000000),
])
def test_result_stored_as_integer_grams(db, training, kilograms, grams):
    reply = training.save_result(-100, 2, 1, kilograms + "*8")
    assert f"{kilograms} кг × 8" in reply.text
    with db.transaction() as s:
        assert s.execute(text("SELECT weight_g, typeof(weight_g) FROM set_results")).one() == (grams, "integer")
        assert "weight_kg" not in {c["name"] for c in inspect(s.connection()).get_columns("set_results")}


def test_numeric_sql_comparisons_and_aggregates(db, training):
    for message_id, kilograms in enumerate(["32.125", "50", "80", "100"], 1):
        training.save_result(-100, 2, message_id, kilograms + "*8")
    with db.transaction() as s:
        assert s.execute(text("SELECT MIN(weight_g), MAX(weight_g), SUM(weight_g), AVG(weight_g) FROM set_results")).one() == (32125, 100000, 262125, 65531.25)
        assert s.scalars(text("SELECT weight_g FROM set_results WHERE weight_g > 80000 ORDER BY weight_g")).all() == [100000]
        assert s.scalars(text("SELECT weight_g FROM set_results ORDER BY weight_g")).all() == [32125, 50000, 80000, 100000]


@pytest.mark.parametrize("invalid_grams", [0, -1, 1.5, 2000001])
def test_database_rejects_invalid_grams(db, training, invalid_grams):
    training.save_result(-100, 2, 1, "50*8")
    with pytest.raises(IntegrityError), db.transaction() as s:
        s.execute(text("UPDATE set_results SET weight_g = :weight"), {"weight": invalid_grams})


def test_history_and_undo_show_kilograms(db, training):
    training.save_result(-100, 2, 1, "32.125*8")
    press(training, training.command(-100, 2, 10, "/finish_train"), "Завершить")
    reply = press(training, training.start_choices(-100, 2), "Вторник")
    card = press(training, reply, "Начать")
    assert "Прошлый раз: 32.125 кг × 8" in card.text
    training.save_result(-100, 2, 2, "32.5*8")
    undo = training.command(-100, 2, 11, "/undo")
    assert "32.5 кг" in undo.text
    assert "32500" not in undo.text


def test_migration_roundtrip_preserves_results_and_indexes(db, training):
    training.save_result(-100, 2, 1, "32.125*8")
    training.save_result(-100, 2, 2, "80*8")
    training.save_result(-100, 3, 3, "100*10")
    training.command(-100, 2, 10, "/undo")
    with db.transaction() as s:
        before = [dict(row) for row in s.execute(text("SELECT * FROM set_results ORDER BY id")).mappings()]
        indexes = {i["name"] for i in inspect(s.connection()).get_indexes("set_results")}
    config = Config("alembic.ini")
    command.downgrade(config, "0001")
    with db.transaction() as s:
        assert s.execute(text("SELECT weight_kg, typeof(weight_kg) FROM set_results ORDER BY id")).all() == [("32.125", "text"), ("80", "text"), ("100", "text")]
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)
    with db.transaction() as s:
        after = [dict(row) for row in s.execute(text("SELECT * FROM set_results ORDER BY id")).mappings()]
        assert after == before
        assert {i["name"] for i in inspect(s.connection()).get_indexes("set_results")} == indexes
        assert not s.execute(text("PRAGMA foreign_key_check")).all()
    assert "xRust — подход 2/4" in training.status(-100, 2).text
    assert "Tim — подход 2/3" in training.status(-100, 2).text


@pytest.mark.parametrize("invalid_kg", ["32.1251", "NaN", "0", "2000.001"])
def test_migration_rejects_unrepresentable_values_atomically(db, training, invalid_kg):
    training.save_result(-100, 2, 1, "32.125*8")
    config = Config("alembic.ini")
    command.downgrade(config, "0001")
    with db.transaction() as s:
        s.execute(text("UPDATE set_results SET weight_kg = :weight"), {"weight": invalid_kg})
    with pytest.raises(RuntimeError, match="целыми граммами"):
        command.upgrade(config, "head")
    with db.transaction() as s:
        columns = {c["name"] for c in inspect(s.connection()).get_columns("set_results")}
        assert "weight_kg" in columns and "weight_g" not in columns
        assert s.scalar(text("SELECT weight_kg FROM set_results")) == invalid_kg
        assert s.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
