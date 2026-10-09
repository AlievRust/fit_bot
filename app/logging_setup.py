"""Последняя защита от случайного токена в сообщениях сторонних библиотек."""

import logging
import traceback


class SecretFilter(logging.Filter):
    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def filter(self, record):
        record.msg = record.getMessage().replace(self.token, "[СКРЫТО]")
        record.args = ()
        if record.exc_info:
            record.exc_text = "".join(traceback.format_exception(*record.exc_info)).replace(self.token, "[СКРЫТО]")
            record.exc_info = None
        return True


def protect_logs(token: str) -> None:
    for handler in logging.getLogger().handlers:
        handler.addFilter(SecretFilter(token))
