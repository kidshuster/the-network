from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.config import Settings
from bot.db.repositories import NetworkRepository, ProfileRepository
from bot.domain.profile_image import ProfileImage
from bot.services.emoji_service import EmojiService
from bot.services.image_service import normalize_image_bytes
from bot.services.profile_cache import ProfileCache
from bot.services.profile_sync import ProfileSyncService
from bot.services.routing_service import RoutingService


def _settings() -> Settings:
    return Settings(_env_file=None, DISCORD_TOKEN="test-token", GUILD_ID=100)


def _png_image() -> ProfileImage:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (32, 32), (1, 2, 3)).save(buffer, format="PNG")
    return normalize_image_bytes(buffer.getvalue())


@pytest.mark.asyncio
async def test_sync_thread_uses_provided_profile_image_without_attachments(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    routing = RoutingService(network_repo)
    cache = ProfileCache(profile_repo)
    emoji_service = EmojiService()
    sync = ProfileSyncService(
        profile_repo,
        network_repo,
        routing,
        cache,
        emoji_service,
        _settings(),
    )

    await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    await routing.load_cache()

    image = _png_image()
    embed = discord.Embed(title="Test Server")
    embed.add_field(name="Server name", value="Test Server", inline=True)
    embed.add_field(name="Source channel", value="<#201>", inline=True)
    embed.add_field(name="Network", value="`stingers`", inline=True)
    embed.add_field(name="Display name", value="Test Server", inline=True)
    embed.add_field(name="Status", value="Enabled", inline=True)

    starter = MagicMock(spec=discord.Message)
    starter.id = 5001
    starter.content = "\u200b"
    starter.attachments = []
    starter.embeds = [embed]

    guild = MagicMock(id=100)
    guild.emojis = []
    created_emoji = MagicMock(spec=discord.Emoji)
    created_emoji.id = 777
    created_emoji.name = "net_test_server_000201"
    guild.create_custom_emoji = AsyncMock(return_value=created_emoji)

    source_channel = MagicMock(spec=discord.TextChannel)
    source_channel.id = 201
    source_channel.type = discord.ChannelType.text
    source_channel.category_id = 200
    guild.get_channel.return_value = source_channel

    thread = MagicMock(spec=discord.Thread)
    thread.id = 5001
    thread.name = "Test Server"

    result = await sync.sync_thread(
        guild,
        thread,
        starter_message=starter,
        profile_image=image,
    )
    assert result.success is True
    assert result.profile is not None
    assert result.profile.emoji_id == 777
    guild.create_custom_emoji.assert_called_once()
