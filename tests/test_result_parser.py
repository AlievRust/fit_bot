from decimal import Decimal

import pytest

from app.parsers.result import parse_result
from app.services.access import BotError


@pytest.mark.parametrize("text,reps,weight,rating", [
    ("50*8", 8, "50", None), ("32.5*10", 10, "32.5", None),
    ("32,5*10", 10, "32.5", None), ("50*8 легко", 8, "50", "easy"),
    ("32.125*8", 8, "32.125", None), ("32,125*8", 8, "32.125", None),
    ("50×8 норм", 8, "50", "normal"), ("50х8 тяжело", 8, "50", "hard"),
])
def test_parse(text, reps, weight, rating):
    result = parse_result(text)
    assert (result.reps, result.weight, result.rating) == (reps, Decimal(weight), rating)


@pytest.mark.parametrize("text", ["текст", "сделал 50*8", "50*0", "-50*8", "0*8", "50*-8", "2001*8", "50*1001", "50*8 потом ещё", "50.0001*8", "NaN*8"])
def test_invalid(text):
    with pytest.raises(BotError):
        parse_result(text)
