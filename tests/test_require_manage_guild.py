from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import discord
import pytest
from discord import app_commands

from bot.cogs._checks import ensure_manage_guild, require_manage_guild
from bot.messages import render_text


@require_manage_guild()
async def _checked_command(interaction: discord.Interaction) -> bool:
    return True


async def _run_manage_guild_check(interaction: discord.Interaction) -> None:
    for check in _checked_command.__discord_app_commands_checks__:
        await check(interaction)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("guild", "user", "manage_guild", "expected_message"),
    [
        (None, MagicMock(spec=discord.Member), True, "This command can only be used in a server."),
        (
            MagicMock(spec=discord.Guild),
            MagicMock(spec=discord.User),
            False,
            "You need **Manage Server** permission to run admin commands.",
        ),
        (
            MagicMock(spec=discord.Guild),
            MagicMock(spec=discord.Member),
            False,
            "You need **Manage Server** permission to run admin commands.",
        ),
    ],
)
async def test_require_manage_guild_rejects(
    guild: discord.Guild | None,
    user: discord.User | discord.Member,
    manage_guild: bool,
    expected_message: str,
) -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = user
    if guild is not None and isinstance(user, MagicMock):
        perms = MagicMock()
        perms.manage_guild = manage_guild
        type(user).guild_permissions = PropertyMock(return_value=perms)

    with pytest.raises(app_commands.CheckFailure, match=expected_message.replace("*", r"\*")):
        await _run_manage_guild_check(interaction)


@pytest.mark.asyncio
async def test_require_manage_guild_allows_manage_guild_member() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    member = MagicMock(spec=discord.Member)
    perms = MagicMock()
    perms.manage_guild = True
    type(member).guild_permissions = MagicMock(return_value=perms)
    interaction.user = member

    await _run_manage_guild_check(interaction)


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
