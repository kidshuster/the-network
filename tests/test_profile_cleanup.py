from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.db.repositories import NetworkRepository, ProfileRepository, RelayRecordRepository
from bot.domain.profile import ServerProfile
from bot.services.emoji_service import EmojiService
from bot.services.profile_cache import ProfileCache
from bot.services.profile_cleanup import ProfileCleanupService


def _profile(*, forum_id: int | None = 801) -> ServerProfile:
    return ServerProfile(
        id=1,
        guild_id=100,
        profile_thread_id=501,
        profile_starter_message_id=502,
        source_channel_id=601,
        network_id=10,
        server_name="Partner",
        display_name="Partner",
        enabled=True,
        emoji_id=901,
        emoji_name="net_partner_123456",
        image_hash="abc",
        degraded_reason=None,
        partner_role_id=701,
        profile_forum_channel_id=forum_id,
    )


@pytest.mark.asyncio
async def test_cleanup_by_thread_deletes_feed_forum_role_and_record(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="net-a",
        display_name="Net A",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
        profile_forum_channel_id=999,
    )
    profile = _profile(forum_id=801)
    await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=profile.profile_thread_id,
        profile_starter_message_id=profile.profile_starter_message_id,
        source_channel_id=profile.source_channel_id,
        network_id=network.id,
        server_name=profile.server_name,
        display_name=profile.display_name,
        enabled=True,
        partner_role_id=701,
        profile_forum_channel_id=801,
    )
    await profile_repo.update_emoji_fields(
        profile.profile_thread_id,
        emoji_id=901,
        emoji_name="net_partner_123456",
        image_hash="abc",
        degraded_reason=None,
    )

    cache = ProfileCache(profile_repo)
    await cache.load_cache()
    emoji_service = MagicMock(spec=EmojiService)
    emoji_service.delete_emoji = AsyncMock()
    cleanup = ProfileCleanupService(
        profile_repo, network_repo, cache, emoji_service, RelayRecordRepository(db)
    )

    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    feed = MagicMock(spec=discord.TextChannel)
    feed.delete = AsyncMock()
    forum = MagicMock(spec=discord.ForumChannel)
    forum.delete = AsyncMock()
    role = MagicMock(spec=discord.Role)
    role.delete = AsyncMock()

    def get_channel(channel_id: int) -> discord.abc.GuildChannel | None:
        if channel_id == 601:
            return feed
        if channel_id == 801:
            return forum
        return None

    guild.get_channel = MagicMock(side_effect=get_channel)
    guild.get_role = MagicMock(return_value=role)

    result = await cleanup.cleanup_by_thread_id(guild, 501, parent_forum_id=801)

    assert result is not None
    assert result.deleted_record is True
    feed.delete.assert_awaited_once()
    forum.delete.assert_awaited_once()
    role.delete.assert_awaited_once()
    emoji_service.delete_emoji.assert_awaited_once_with(guild, 901)
    assert await profile_repo.get_by_thread_id(501) is None


@pytest.mark.asyncio
async def test_cleanup_by_feed_skips_already_deleted_feed(db) -> None:
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
        profile_thread_id=501,
        profile_starter_message_id=502,
        source_channel_id=601,
        network_id=network.id,
        server_name="Partner",
        display_name="Partner",
        enabled=True,
        partner_role_id=701,
        profile_forum_channel_id=801,
    )

    cache = ProfileCache(profile_repo)
    emoji_service = MagicMock(spec=EmojiService)
    emoji_service.delete_emoji = AsyncMock()
    cleanup = ProfileCleanupService(
        profile_repo, network_repo, cache, emoji_service, RelayRecordRepository(db)
    )

    guild = MagicMock(spec=discord.Guild)
    forum = MagicMock(spec=discord.ForumChannel)
    forum.delete = AsyncMock()
    role = MagicMock(spec=discord.Role)
    role.delete = AsyncMock()
    guild.get_channel = MagicMock(side_effect=lambda cid: forum if cid == 801 else None)
    guild.get_role = MagicMock(return_value=role)

    result = await cleanup.cleanup_by_feed_channel_id(guild, 601)

    assert result is not None
    forum.delete.assert_awaited_once()
    role.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_by_network_id_deletes_all_servers(db) -> None:
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
    for index, thread_id in enumerate((501, 502), start=1):
        await profile_repo.upsert(
            guild_id=100,
            profile_thread_id=thread_id,
            profile_starter_message_id=thread_id + 100,
            source_channel_id=600 + index,
            network_id=network.id,
            server_name=f"Partner {index}",
            display_name=f"Partner {index}",
            enabled=True,
            partner_role_id=700 + index,
            profile_forum_channel_id=800 + index,
        )

    cache = ProfileCache(profile_repo)
    emoji_service = MagicMock(spec=EmojiService)
    emoji_service.delete_emoji = AsyncMock()
    cleanup = ProfileCleanupService(
        profile_repo, network_repo, cache, emoji_service, RelayRecordRepository(db)
    )

    guild = MagicMock(spec=discord.Guild)

    def get_channel(channel_id: int) -> discord.abc.GuildChannel | None:
        channel = MagicMock()
        channel.delete = AsyncMock()
        return channel

    guild.get_channel = MagicMock(side_effect=get_channel)
    guild.get_role = MagicMock(return_value=None)

    results = await cleanup.cleanup_by_network_id(guild, network.id)

    assert len(results) == 2
    assert await profile_repo.list_by_network_id(network.id) == []


@pytest.mark.asyncio
async def test_cleanup_deletes_relay_records_before_profile(db) -> None:
    from bot.constants import RelayStatus

    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    relay_repo = RelayRecordRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="net-relay",
        display_name="Net Relay",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    profile = await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=501,
        profile_starter_message_id=502,
        source_channel_id=601,
        network_id=network.id,
        server_name="Partner",
        display_name="Partner",
        enabled=True,
    )
    await relay_repo.create_pending(
        source_message_id=9001,
        source_channel_id=601,
        source_webhook_id=777,
        profile_id=profile.id,
        network_id=network.id,
        destination_channel_id=300,
    )
    await relay_repo.update_status(
        (await relay_repo.get_by_source_message(9001)).id,  # type: ignore[union-attr]
        status=RelayStatus.PUBLISHED,
        destination_message_ids=(9100,),
    )

    cache = ProfileCache(profile_repo)
    emoji_service = MagicMock(spec=EmojiService)
    emoji_service.delete_emoji = AsyncMock()
    cleanup = ProfileCleanupService(
        profile_repo, network_repo, cache, emoji_service, relay_repo
    )

    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock()
    channel.delete = AsyncMock()
    guild.get_channel = MagicMock(return_value=channel)
    guild.get_role = MagicMock(return_value=None)
    guild.get_thread = MagicMock(return_value=None)
    guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "missing"))

    result = await cleanup.cleanup_server(guild, profile)

    assert result is not None
    assert result.deleted_record is True
    assert await relay_repo.get_by_source_message(9001) is None

