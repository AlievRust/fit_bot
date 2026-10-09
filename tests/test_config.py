import pytest
from pydantic import ValidationError

from app.config import Config


def test_env_and_secret(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:secret")
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "123456789012")
    config = Config.from_env()
    assert config.owner_telegram_id == 123456789012
    assert "123:secret" not in repr(config)


@pytest.mark.parametrize("token,owner", [("", 1), ("ok", 0), ("ok", -1)])
def test_invalid_config(token, owner):
    with pytest.raises(ValidationError):
        Config(bot_token=token, owner_telegram_id=owner)
