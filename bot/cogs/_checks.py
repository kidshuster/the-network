from __future__ import annotations

from collections.abc import Callable
from typing import Any

import discord
from discord import app_commands

from bot.messages import render_text


async def ensure_manage_guild(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.guild_permissions.manage_guild:
        await interaction.response.send_message(
            render_text("manage_guild_required"),
            ephemeral=True,
        )
        return False
    return True


def require_manage_guild() -> Callable[[Any], Any]:
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can only be used in a server.")
        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.CheckFailure(
                "You need **Manage Server** permission to run admin commands."
            )
        if not member.guild_permissions.manage_guild:
            raise app_commands.CheckFailure(
                "You need **Manage Server** permission to run admin commands."
            )
        return True

    return app_commands.check(predicate)
