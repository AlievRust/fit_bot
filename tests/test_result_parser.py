from decimal import Decimal

import pytest

from app.parsers.result import parse_result
from app.services.access import BotError


@pytest.mark.parametrize("text,reps,weight,rating", [
    ("8*50", 8, "50", None), ("10*32.5", 10, "32.5", None),
    ("10*32,5", 10, "32.5", None), ("8*50 легко", 8, "50", "easy"),
    ("8*32.125", 8, "32.125", None), ("8*32,125", 8, "32.125", None),
    ("8×50 норм", 8, "50", "normal"), ("8х50 тяжело", 8, "50", "hard"),
])
def test_parse(text, reps, weight, rating):
    result = parse_result(text)
    assert (result.reps, result.weight, result.rating) == (reps, Decimal(weight), rating)


@pytest.mark.parametrize("text", ["текст", "сделал 8*50", "0*50", "-8*50", "8*0", "8*-50", "8*2001", "1001*50", "8*50 потом ещё", "8*50.0001", "8*NaN"])
def test_invalid(text):
    with pytest.raises(BotError):
        parse_result(text)
