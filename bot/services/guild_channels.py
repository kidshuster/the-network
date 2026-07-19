from __future__ import annotations

import discord

from bot.domain.network import Network
from bot.services.guild_layout import (
    CATEGORY_NETWORK,
    CHANNEL_JOIN_REQUESTS,
    join_channel_name,
    resolve_category,
    resolve_join_requests_channel,
    resolve_network_hub_category,
    resolve_text_channel_in_category,
)

# Backwards-compatible aliases
_NETWORK_HUB_CATEGORY_NAME = CATEGORY_NETWORK.casefold()
_JOIN_REQUESTS_CHANNEL_NAME = CHANNEL_JOIN_REQUESTS
_JOIN_CHANNEL_PREFIX = "join-"


def resolve_network_join_channel(
    guild: discord.Guild,
    network: Network,
) -> discord.TextChannel | None:
    if network.join_channel_id is not None:
        channel = guild.get_channel(network.join_channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel

    expected_name = join_channel_name(network.key).casefold()
    hub_category = resolve_network_hub_category(guild)
    for channel in guild.text_channels:
        if channel.name.casefold() != expected_name:
            continue
        if hub_category is not None and channel.category_id != hub_category.id:
            continue
        return channel
    return None


__all__ = [
    "join_channel_name",
    "resolve_category",
    "resolve_join_requests_channel",
    "resolve_network_hub_category",
    "resolve_network_join_channel",
    "resolve_text_channel_in_category",
]
