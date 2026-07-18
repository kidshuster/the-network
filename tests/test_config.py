from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from bot.config import Settings


def test_settings_requires_discord_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "")
    monkeypatch.setenv("GUILD_ID", "123456789012345678")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_requires_guild_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_loads_valid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "123456789012345678")
    monkeypatch.setenv("DATABASE_PATH", "./data/test-relay.db")
    monkeypatch.setenv("MANUAL_RELAY_ENABLED", "true")

    settings = Settings(_env_file=None)

    assert settings.discord_token == "test-token"
    assert settings.guild_id == 123456789012345678
    assert settings.database_path == Path("./data/test-relay.db")
    assert settings.manual_relay_enabled is True


def test_settings_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=file-token\nGUILD_ID=987654321098765432\nDATABASE_PATH=./data/from-env.db\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("GUILD_ID", raising=False)

    settings = Settings()

    assert settings.discord_token == "file-token"
    assert settings.guild_id == 987654321098765432
