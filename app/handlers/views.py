"""Ответы сервисов без зависимости от Telegram API."""

from dataclasses import dataclass, field


@dataclass
class Reply:
    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)
