from __future__ import annotations

import discord

from bot.app.templates import render_text


async def ensure_manage_guild(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.guild_permissions.manage_guild:
        await interaction.response.send_message(
            render_text("manage_guild_required"),
            ephemeral=True,
        )
        return False
    return True
