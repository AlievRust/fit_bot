"""Последняя защита от случайного токена в сообщениях сторонних библиотек."""

import logging
import traceback


class SecretFilter(logging.Filter):
    """Маскировать известный токен в готовом сообщении и тексте исключения."""

    def __init__(self, token: str):
        """Сохранить токен, который нужно удалять из записей журнала."""
        super().__init__()
        self.token = token

    def filter(self, record):
        """Изменить запись на месте и разрешить её дальнейшую обработку."""
        record.msg = record.getMessage().replace(self.token, "[СКРЫТО]")
        # getMessage уже подставил аргументы; повторная подстановка не нужна.
        record.args = ()
        if record.exc_info:
            # Форматируем traceback сами, чтобы токен был скрыт и в исключениях.
            record.exc_text = "".join(traceback.format_exception(*record.exc_info)).replace(self.token, "[СКРЫТО]")
            record.exc_info = None
        return True


def protect_logs(token: str) -> None:
    """Установить фильтр на уже настроенные обработчики корневого логгера."""
    for handler in logging.getLogger().handlers:
        handler.addFilter(SecretFilter(token))
