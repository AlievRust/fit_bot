"""Ответы сервисов без зависимости от Telegram API."""

from dataclasses import dataclass, field


@dataclass
class Reply:
    """Ответ сервиса: текст и строки кнопок вида (подпись, callback_data).

    Telegram-адаптер превращает эти данные в сообщения и клавиатуру.
    default_factory создаёт отдельный список кнопок для каждого ответа.
    """

    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)
