from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.adapters.discord.checks import ensure_manage_guild
from bot.core.widgets import render_text


@pytest.mark.asyncio
async def test_ensure_manage_guild_sends_popup_when_unauthorized() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    member = MagicMock(spec=discord.Member)
    perms = MagicMock()
    perms.manage_guild = False
    member.guild_permissions = perms
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    allowed = await ensure_manage_guild(interaction)

    assert allowed is False
    interaction.response.send_message.assert_awaited_once_with(
        render_text("manage_guild_required"),
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_ensure_manage_guild_allows_manage_guild_member() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    member = MagicMock(spec=discord.Member)
    perms = MagicMock()
    perms.manage_guild = True
    member.guild_permissions = perms
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    allowed = await ensure_manage_guild(interaction)

    assert allowed is True
    interaction.response.send_message.assert_not_called()
