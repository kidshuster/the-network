from __future__ import annotations

import pytest

from bot.config import Settings
from bot.constants import SETTING_PROFILE_FORUM_CHANNEL_ID
from bot.db.repositories import SettingsRepository
from bot.services.bot_settings import BotSettingsService


@pytest.mark.asyncio
async def test_settings_repository_set_and_get(db) -> None:
    repo = SettingsRepository(db)
    assert await repo.get(SETTING_PROFILE_FORUM_CHANNEL_ID) is None
    await repo.set(SETTING_PROFILE_FORUM_CHANNEL_ID, "123456789012345678")
    assert await repo.get(SETTING_PROFILE_FORUM_CHANNEL_ID) == "123456789012345678"
    await repo.set(SETTING_PROFILE_FORUM_CHANNEL_ID, "987654321098765432")
    assert await repo.get(SETTING_PROFILE_FORUM_CHANNEL_ID) == "987654321098765432"


@pytest.mark.asyncio
async def test_bot_settings_prefers_database_over_env(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    monkeypatch.setenv("PROFILE_FORUM_CHANNEL_ID", "111111111111111111")
    env_settings = Settings(_env_file=None)

    repo = SettingsRepository(db)
    await repo.set(SETTING_PROFILE_FORUM_CHANNEL_ID, "222222222222222222")

    service = BotSettingsService(repo, env_settings)
    await service.load()
    assert service.profile_forum_channel_id == 222222222222222222


@pytest.mark.asyncio
async def test_bot_settings_falls_back_to_env(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    monkeypatch.setenv("PROFILE_FORUM_CHANNEL_ID", "333333333333333333")
    env_settings = Settings(_env_file=None)

    service = BotSettingsService(SettingsRepository(db), env_settings)
    await service.load()
    assert service.profile_forum_channel_id == 333333333333333333


@pytest.mark.asyncio
async def test_bot_settings_set_profile_forum(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    env_settings = Settings(_env_file=None)

    service = BotSettingsService(SettingsRepository(db), env_settings)
    await service.load()
    await service.set_profile_forum_channel_id(444444444444444444)
    assert service.profile_forum_channel_id == 444444444444444444

    reloaded = BotSettingsService(SettingsRepository(db), env_settings)
    await reloaded.load()
    assert reloaded.profile_forum_channel_id == 444444444444444444
