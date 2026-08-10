from __future__ import annotations

import pytest

from bot.db.repositories import SettingsRepository


@pytest.mark.asyncio
async def test_get_returns_none_for_missing_key(db) -> None:
    repo = SettingsRepository(db)
    assert await repo.get("missing_key") is None


@pytest.mark.asyncio
async def test_set_and_get_round_trip(db) -> None:
    repo = SettingsRepository(db)
    await repo.set("hub_join_the_network_sticky", "123:456")
    assert await repo.get("hub_join_the_network_sticky") == "123:456"


@pytest.mark.asyncio
async def test_set_upserts_existing_key(db) -> None:
    repo = SettingsRepository(db)
    await repo.set("profile_forum_channel_id", "100")
    await repo.set("profile_forum_channel_id", "200")
    assert await repo.get("profile_forum_channel_id") == "200"
