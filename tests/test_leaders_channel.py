from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.guild_permissions import build_leaders_channel_overwrites
from bot.services.leaders_channel import apply_leaders_channel_permissions


def test_leaders_channel_overwrites_hide_everyone_and_grant_client_roles() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    client_a = MagicMock(spec=discord.Role)
    client_a.id = 101
    client_a.position = 1
    client_b = MagicMock(spec=discord.Role)
    client_b.id = 102
    client_b.position = 2

    access = MagicMock(spec=discord.Role)
    access.id = 201
    access.position = 3

    overwrites = dict(
        build_leaders_channel_overwrites(
            guild,
            bot_member,
            [client_a, client_b],
            access,
            None,
        )
    )

    assert overwrites[everyone].view_channel is False
    assert overwrites[client_a].view_channel is True
    assert overwrites[client_a].send_messages is True
    assert overwrites[client_b].send_messages is True
    assert overwrites[access].view_channel is False


@pytest.mark.asyncio
async def test_apply_leaders_channel_permissions_disables_category_sync() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.edit = AsyncMock()
    everyone = MagicMock(spec=discord.Role)
    overwrites = {everyone: discord.PermissionOverwrite(view_channel=False)}

    await apply_leaders_channel_permissions(
        channel,
        overwrites,
        reason="test",
    )

    channel.edit.assert_awaited_once_with(
        sync_permissions=False,
        overwrites=overwrites,
        reason="test",
    )


@pytest.mark.asyncio
async def test_apply_leaders_channel_permissions_can_move_category() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.edit = AsyncMock()
    category = MagicMock(spec=discord.CategoryChannel)
    everyone = MagicMock(spec=discord.Role)
    overwrites = {everyone: discord.PermissionOverwrite(view_channel=False)}

    await apply_leaders_channel_permissions(
        channel,
        overwrites,
        reason="test",
        category=category,
    )

    channel.edit.assert_awaited_once_with(
        sync_permissions=False,
        overwrites=overwrites,
        reason="test",
        category=category,
    )
