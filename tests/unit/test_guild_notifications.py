from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import discord
import pytest

from bot.features.hub.notifications import (
    count_hub_guild_channels,
    ensure_guild_only_mention_notifications,
    sync_guild_notification_policy,
)


def _guild_with_channels(*, default: discord.NotificationLevel) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.default_notifications = default
    guild.channels = [MagicMock(spec=discord.TextChannel), MagicMock(spec=discord.VoiceChannel)]
    guild.edit = AsyncMock()
    bot = MagicMock(spec=discord.Member)
    type(bot).guild_permissions = PropertyMock(
        return_value=MagicMock(manage_guild=True),
    )
    return guild, bot


@pytest.mark.asyncio
async def test_ensure_guild_only_mention_notifications_updates_guild() -> None:
    guild, bot = _guild_with_channels(default=discord.NotificationLevel.all_messages)

    changed, error = await ensure_guild_only_mention_notifications(
        guild,
        bot,
        reason="test",
    )

    assert changed is True
    assert error is None
    guild.edit.assert_awaited_once_with(
        default_notifications=discord.NotificationLevel.only_mentions,
        reason="test",
    )


@pytest.mark.asyncio
async def test_ensure_guild_only_mention_notifications_skips_when_already_set() -> None:
    guild, bot = _guild_with_channels(default=discord.NotificationLevel.only_mentions)

    changed, error = await ensure_guild_only_mention_notifications(
        guild,
        bot,
        reason="test",
    )

    assert changed is False
    assert error is None
    guild.edit.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_guild_only_mention_notifications_without_manage_guild() -> None:
    guild, bot = _guild_with_channels(default=discord.NotificationLevel.all_messages)
    type(bot).guild_permissions = PropertyMock(
        return_value=MagicMock(manage_guild=False),
    )

    changed, error = await ensure_guild_only_mention_notifications(
        guild,
        bot,
        reason="test",
    )

    assert changed is False
    assert error == "bot needs **Manage Server**"
    guild.edit.assert_not_called()


def test_count_hub_guild_channels() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.channels = [
        MagicMock(spec=discord.TextChannel),
        MagicMock(spec=discord.CategoryChannel),
        MagicMock(spec=discord.Thread),
    ]

    assert count_hub_guild_channels(guild) == 2


@pytest.mark.asyncio
async def test_sync_guild_notification_policy_appends_note() -> None:
    guild, bot = _guild_with_channels(default=discord.NotificationLevel.all_messages)
    result = MagicMock()
    result.notes = []

    await sync_guild_notification_policy(
        guild,
        bot,
        reason="test",
        result=result,
    )

    assert result.notes
    assert "Only @mentions" in result.notes[0]
    assert "2" in result.notes[0]
