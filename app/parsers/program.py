"""Ограниченный YAML schema_version=1 с полной валидацией до записи."""

import re
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator, model_validator
from yaml.tokens import AliasToken, AnchorToken

from app.services.access import BotError

MAX_IMPORT_BYTES = 128 * 1024
Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Name = Annotated[str, Field(min_length=1, max_length=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProgramInfo(StrictModel):
    key: Key
    name: Name
    version: Annotated[StrictInt, Field(ge=1, le=2**31 - 1)]


class AthleteInfo(StrictModel):
    key: Key
    display_name: Name


class SetPlan(StrictModel):
    reps: str
    rir: Annotated[StrictInt, Field(ge=0, le=10)] | None = None

    @field_validator("reps")
    @classmethod
    def valid_reps(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9][0-9]{0,3}(?:-[1-9][0-9]{0,3})?", value):
            raise ValueError('Повторы задаются строкой "8" или "6-8"')
        low, high = reps_bounds(value)
        if not 1 <= low <= high <= 1000:
            raise ValueError("Неверный диапазон повторов")
        return value


def reps_bounds(value: str) -> tuple[int, int]:
    parts = value.split("-")
    return int(parts[0]), int(parts[-1])


class ExerciseInfo(StrictModel):
    key: Key
    name: Name
    order: Annotated[StrictInt, Field(ge=1, le=1000)]
    prescriptions: Annotated[dict[Key, Annotated[list[SetPlan], Field(min_length=1, max_length=20)]], Field(min_length=1, max_length=20)]


class DayInfo(StrictModel):
    key: Key
    name: Name
    exercises: Annotated[list[ExerciseInfo], Field(min_length=1, max_length=30)]

    @model_validator(mode="after")
    def unique_exercises(self):
        if len({e.key for e in self.exercises}) != len(self.exercises) or len({e.order for e in self.exercises}) != len(self.exercises):
            raise ValueError("Ключи и порядок упражнений дня должны быть уникальны")
        return self


class ProgramDocument(StrictModel):
    schema_version: StrictInt
    program: ProgramInfo
    athletes: Annotated[list[AthleteInfo], Field(min_length=1, max_length=20)]
    days: Annotated[list[DayInfo], Field(min_length=1, max_length=14)]

    @model_validator(mode="after")
    def validate_references(self):
        if self.schema_version != 1:
            raise ValueError("Поддерживается только schema_version: 1")
        keys = {a.key for a in self.athletes}
        if len(keys) != len(self.athletes) or len({d.key for d in self.days}) != len(self.days):
            raise ValueError("Ключи спортсменов и дней должны быть уникальны")
        for day in self.days:
            for exercise in day.exercises:
                if set(exercise.prescriptions) - keys:
                    raise ValueError("В prescriptions указан неизвестный athlete")
        return self


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, (str, int)) or key in mapping:
            raise ValueError("Неверный или повторный ключ YAML")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def parse_program(data: bytes) -> ProgramDocument:
    if not data or len(data) > MAX_IMPORT_BYTES:
        raise BotError("YAML должен быть непустым и не больше 128 КиБ.")
    try:
        text = data.decode("utf-8-sig")
        if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(text)):
            raise ValueError("YAML aliases/anchors не поддерживаются")
        raw = yaml.load(text, Loader=UniqueLoader)
        return ProgramDocument.model_validate(raw)
    except (UnicodeError, yaml.YAMLError, ValueError, RecursionError) as exc:
        if isinstance(exc, ValidationError):
            location = ".".join(str(part) for part in exc.errors()[0]["loc"])
            detail = f" Проверьте поле {location}." if location else ""
        else:
            detail = " Проверьте структуру, уникальность ключей и кодировку UTF-8."
        raise BotError("Импорт отклонён: неверная схема YAML." + detail) from None
