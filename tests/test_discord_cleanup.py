from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.discord_cleanup import wipe_text_channel


@pytest.mark.asyncio
async def test_wipe_text_channel_requires_manage_messages() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 100
    channel.permissions_for.return_value = discord.PermissionOverwrite(
        view_channel=True,
        manage_messages=False,
    )
    bot_member = MagicMock(spec=discord.Member)

    deleted, error = await wipe_text_channel(channel, bot_member)

    assert deleted == 0
    assert error is not None
    assert "Manage Messages" in error


@pytest.mark.asyncio
async def test_wipe_text_channel_purges_then_deletes_remaining() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 100
    channel.permissions_for.return_value = discord.PermissionOverwrite(
        view_channel=True,
        manage_messages=True,
    )
    bot_member = MagicMock(spec=discord.Member)

    old_message = MagicMock(spec=discord.Message)
    old_message.id = 1
    old_message.delete = AsyncMock()

    purge_batches = [[MagicMock(spec=discord.Message), MagicMock(spec=discord.Message)], []]

    async def purge(limit: int = 100):
        return purge_batches.pop(0) if purge_batches else []

    channel.purge = purge

    async def history(limit=None):
        yield old_message

    channel.history = history

    deleted, error = await wipe_text_channel(channel, bot_member)

    assert error is None
    assert deleted == 3
    old_message.delete.assert_awaited_once()
