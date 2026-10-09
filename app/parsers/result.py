"""Полное соответствие формату повторы*вес [оценка]."""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.services.access import BotError

PATTERN = re.compile(r"\s*([1-9][0-9]{0,3})\s*[*xх×]\s*([0-9]{1,4}(?:[.,][0-9]{1,3})?)(?:\s+(легко|норм|тяжело))?\s*", re.IGNORECASE)
RATINGS = {"легко": "easy", "норм": "normal", "тяжело": "hard"}


@dataclass(frozen=True)
class ParsedResult:
    reps: int
    weight: Decimal
    rating: str | None


def parse_result(text: str) -> ParsedResult:
    match = PATTERN.fullmatch(text)
    if not match:
        raise BotError("Результат: повторы*вес, например 8*50 или 10*32,5 тяжело.")
    reps = int(match[1])
    weight = Decimal(match[2].replace(",", "."))
    if reps > 1000 or not 0 < weight <= 2000:
        raise BotError("Допустимо 1–1000 повторов и вес больше 0, до 2000 кг.")
    return ParsedResult(reps, weight, RATINGS.get((match[3] or "").lower()))
