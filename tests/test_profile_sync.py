from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.config import Settings
from bot.db.repositories import NetworkRepository, ProfileRepository
from bot.services.emoji_service import EmojiService
from bot.services.profile_cache import ProfileCache
from bot.services.profile_sync import ProfileSyncService
from bot.services.routing_service import RoutingService


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        DISCORD_TOKEN="test-token",
        GUILD_ID=100,
    )


@pytest.mark.asyncio
async def test_sync_infers_network_from_feed_category(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    routing = RoutingService(network_repo)
    cache = ProfileCache(profile_repo)
    emoji = EmojiService()
    sync = ProfileSyncService(profile_repo, network_repo, routing, cache, emoji, _settings())

    await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    await routing.load_cache()

    source_channel = MagicMock(spec=discord.TextChannel)
    source_channel.id = 201
    source_channel.type = discord.ChannelType.text
    source_channel.category_id = 200
    source_channel.guild = MagicMock(id=100)

    guild = MagicMock(id=100)
    guild.get_channel.return_value = source_channel

    thread = MagicMock(spec=discord.Thread)
    thread.id = 5001
    thread.name = "Partner Server"
    starter = MagicMock(spec=discord.Message)
    starter.id = 5001
    starter.content = "server_name: Partner\nsource_channel: <#201>\nenabled: true\n"
    thread.fetch_message = AsyncMock(return_value=starter)

    result = await sync.sync_thread(guild, thread)
    assert result.success is True
    assert result.profile is not None
    assert result.profile.source_channel_id == 201
    assert result.profile.network_id == 1


@pytest.mark.asyncio
async def test_sync_parse_failure_preserves_existing(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    routing = RoutingService(network_repo)
    cache = ProfileCache(profile_repo)
    emoji = EmojiService()
    sync = ProfileSyncService(profile_repo, network_repo, routing, cache, emoji, _settings())

    network = await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
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
        server_name="Partner",
        display_name="Partner",
        enabled=True,
    )

    source_channel = MagicMock(spec=discord.TextChannel)
    source_channel.id = 201
    source_channel.type = discord.ChannelType.text
    source_channel.category_id = 200

    guild = MagicMock(id=100)
    guild.get_channel.return_value = source_channel

    thread = MagicMock(spec=discord.Thread)
    thread.id = 5001
    thread.name = "Partner Server"
    starter = MagicMock(spec=discord.Message)
    starter.id = 5001
    starter.content = "source_channel: <#201>\nenabled: maybe\n"
    thread.fetch_message = AsyncMock(return_value=starter)

    result = await sync.sync_thread(guild, thread)
    assert result.success is False
    assert result.preserved_existing is True
    assert result.profile is not None
    assert result.profile.server_name == "Partner"
