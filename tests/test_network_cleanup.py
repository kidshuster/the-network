from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.db.repositories import NetworkRepository, ProfileRepository
from bot.services.network_cleanup import NetworkCleanupService
from bot.services.profile_cache import ProfileCache
from bot.services.profile_cleanup import ProfileCleanupService


@pytest.mark.asyncio
async def test_cleanup_network_deletes_category_and_channels(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="net-a",
        display_name="Net A",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=201,
        profile_forum_channel_id=202,
    )

    cache = ProfileCache(profile_repo)
    profile_cleanup = MagicMock(spec=ProfileCleanupService)
    profile_cleanup.cleanup_by_network_id = AsyncMock(return_value=[])
    service = NetworkCleanupService(profile_cleanup, cache)

    guild = MagicMock(spec=discord.Guild)
    feed = MagicMock(spec=discord.TextChannel)
    feed.id = 203
    feed.category_id = 200
    concat = MagicMock(spec=discord.TextChannel)
    concat.id = 201
    concat.category_id = 200
    forum = MagicMock(spec=discord.ForumChannel)
    forum.id = 202
    forum.category_id = 200
    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 200
    category.delete = AsyncMock()
    feed.delete = AsyncMock()
    concat.delete = AsyncMock()
    forum.delete = AsyncMock()

    guild.channels = [feed, concat, forum, category]
    guild.get_channel = MagicMock(
        side_effect=lambda cid: {
            200: category,
            201: concat,
            202: forum,
            203: feed,
        }.get(cid)
    )

    result = await service.cleanup_network(guild, network)

    assert result.deleted_category is True
    assert result.deleted_channels == 3
    feed.delete.assert_awaited_once()
    concat.delete.assert_awaited_once()
    forum.delete.assert_awaited_once()
    category.delete.assert_awaited_once()
    profile_cleanup.cleanup_by_network_id.assert_awaited_once_with(guild, network.id)
