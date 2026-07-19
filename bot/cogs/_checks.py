from __future__ import annotations

from collections.abc import Callable
from typing import Any

import discord
from discord import app_commands


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


def require_partner_profile_channel() -> Callable[[Any], Any]:
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can only be used in a server.")
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            raise app_commands.CheckFailure(
                "Run this command inside your server profile channel."
            )

        from bot.client import NetworkRelayBot

        bot = interaction.client
        if not isinstance(bot, NetworkRelayBot) or bot.bot_context is None:
            raise app_commands.CheckFailure("Bot is not ready yet.")

        profile = await bot.bot_context.profile_repo.get_by_thread_id(channel.id)
        if profile is None:
            raise app_commands.CheckFailure("This channel is not a registered server profile.")

        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.CheckFailure("Could not resolve your server membership.")

        if member.guild_permissions.manage_guild:
            return True

        if profile.partner_role_id is None:
            raise app_commands.CheckFailure("This profile has no server access role configured.")

        server_role = interaction.guild.get_role(profile.partner_role_id)
        if server_role is None or server_role not in member.roles:
            raise app_commands.CheckFailure(
                "You need the server access role for this profile to update it."
            )
        return True

    return app_commands.check(predicate)


def require_partner_profile_thread() -> Callable[[Any], Any]:
    return require_partner_profile_channel()
