from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from bot.domain.errors import NetworkValidationError
from bot.services.network_validation import validate_network_channels


def _permissions(**flags: bool) -> MagicMock:
    perms = MagicMock()
    for name, value in flags.items():
        setattr(perms, name, value)
    return perms


def _channel(
    *,
    channel_id: int,
    guild_id: int,
    channel_type: discord.ChannelType,
    name: str = "channel",
    category_id: int | None = None,
) -> MagicMock:
    channel = MagicMock(spec=discord.abc.GuildChannel)
    channel.id = channel_id
    channel.name = name
    channel.type = channel_type
    channel.guild = MagicMock(id=guild_id)
    channel.category_id = category_id
    channel.permissions_for = MagicMock(
        return_value=_permissions(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
        )
    )
    return channel


@pytest.mark.asyncio
async def test_validate_accepts_valid_setup() -> None:
    guild = MagicMock(id=100)
    bot_member = MagicMock()
    feed_category = _channel(
        channel_id=1,
        guild_id=100,
        channel_type=discord.ChannelType.category,
        name="feeds",
    )
    output = _channel(
        channel_id=2,
        guild_id=100,
        channel_type=discord.ChannelType.news,
        name="announcements",
    )
    concat = _channel(
        channel_id=3,
        guild_id=100,
        channel_type=discord.ChannelType.text,
        name="audit",
        category_id=1,
    )

    await validate_network_channels(guild, bot_member, feed_category, output, concat)


@pytest.mark.asyncio
async def test_validate_rejects_non_announcement_output() -> None:
    guild = MagicMock(id=100)
    bot_member = MagicMock()
    feed_category = _channel(
        channel_id=1,
        guild_id=100,
        channel_type=discord.ChannelType.category,
    )
    output = _channel(
        channel_id=2,
        guild_id=100,
        channel_type=discord.ChannelType.text,
        name="not-news",
    )

    with pytest.raises(NetworkValidationError, match="announcement"):
        await validate_network_channels(guild, bot_member, feed_category, output, None)


@pytest.mark.asyncio
async def test_validate_rejects_concat_outside_category() -> None:
    guild = MagicMock(id=100)
    bot_member = MagicMock()
    feed_category = _channel(
        channel_id=1,
        guild_id=100,
        channel_type=discord.ChannelType.category,
        name="feeds",
    )
    output = _channel(
        channel_id=2,
        guild_id=100,
        channel_type=discord.ChannelType.news,
    )
    concat = _channel(
        channel_id=3,
        guild_id=100,
        channel_type=discord.ChannelType.text,
        category_id=999,
        name="wrong-cat",
    )

    with pytest.raises(NetworkValidationError, match="inside"):
        await validate_network_channels(guild, bot_member, feed_category, output, concat)


@pytest.mark.asyncio
async def test_validate_reports_missing_permissions() -> None:
    guild = MagicMock(id=100)
    bot_member = MagicMock()
    feed_category = _channel(
        channel_id=1,
        guild_id=100,
        channel_type=discord.ChannelType.category,
    )
    feed_category.permissions_for.return_value = _permissions(
        view_channel=True,
        read_message_history=False,
    )
    output = _channel(
        channel_id=2,
        guild_id=100,
        channel_type=discord.ChannelType.news,
    )

    with pytest.raises(NetworkValidationError, match="read message history"):
        await validate_network_channels(guild, bot_member, feed_category, output, None)
