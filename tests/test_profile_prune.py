from __future__ import annotations

import pytest

from bot.db.repositories import NetworkRepository, ProfileRepository


@pytest.mark.asyncio
async def test_delete_by_thread_id(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="net-a",
        display_name="Net A",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=5001,
        profile_starter_message_id=5001,
        source_channel_id=201,
        network_id=network.id,
        server_name="Alpha",
        display_name="Alpha",
        enabled=True,
    )

    deleted = await profile_repo.delete_by_thread_id(5001)
    assert deleted is not None
    assert deleted.server_name == "Alpha"
    assert await profile_repo.get_by_thread_id(5001) is None
    assert await profile_repo.delete_by_thread_id(9999) is None


@pytest.mark.asyncio
async def test_prune_orphaned_profiles(db) -> None:
    from bot.config import Settings
    from bot.services.emoji_service import EmojiService
    from bot.services.profile_cache import ProfileCache
    from bot.services.profile_sync import ProfileSyncService
    from bot.services.routing_service import RoutingService

    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="net-a",
        display_name="Net A",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=5001,
        profile_starter_message_id=5001,
        source_channel_id=201,
        network_id=network.id,
        server_name="Keep Me",
        display_name="Keep Me",
        enabled=True,
    )
    await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=5002,
        profile_starter_message_id=5002,
        source_channel_id=202,
        network_id=network.id,
        server_name="Delete Me",
        display_name="Delete Me",
        enabled=True,
    )

    settings = Settings(_env_file=None, DISCORD_TOKEN="test-token", GUILD_ID=100)
    sync = ProfileSyncService(
        profile_repo,
        network_repo,
        RoutingService(network_repo),
        ProfileCache(profile_repo),
        EmojiService(),
        settings,
    )
    removed = await sync._prune_orphaned_profiles({5001})
    assert len(removed) == 1
    assert removed[0].server_name == "Delete Me"
    assert await profile_repo.get_by_thread_id(5001) is not None
    assert await profile_repo.get_by_thread_id(5002) is None
