from __future__ import annotations

import discord
from discord import app_commands

from bot.client import NetworkRelayBot


async def network_key_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    bot = interaction.client
    if not isinstance(bot, NetworkRelayBot) or bot.bot_context is None:
        return []
    networks = await bot.bot_context.network_repo.list_all()
    needle = current.casefold()
    choices: list[app_commands.Choice[str]] = []
    for network in networks:
        if needle in network.key.casefold() or needle in network.display_name.casefold():
            choices.append(
                app_commands.Choice(
                    name=f"{network.display_name} ({network.key})",
                    value=network.key,
                )
            )
    return choices[:25]


async def server_name_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    bot = interaction.client
    if not isinstance(bot, NetworkRelayBot) or bot.bot_context is None:
        return []

    network_key = getattr(interaction.namespace, "key", None)
    profiles = await bot.bot_context.profile_repo.list_all()
    if isinstance(network_key, str) and network_key.strip():
        network = await bot.bot_context.network_repo.get_by_key(network_key)
        if network is None:
            return []
        profiles = [
            profile for profile in profiles if profile.network_id == network.id
        ]

    needle = current.casefold()
    choices: list[app_commands.Choice[str]] = []
    seen: set[str] = set()
    for profile in profiles:
        label = profile.server_name
        if needle not in label.casefold():
            continue
        dedupe = label.casefold()
        if dedupe in seen:
            continue
        seen.add(dedupe)
        choices.append(app_commands.Choice(name=label, value=label))
    return choices[:25]
