from __future__ import annotations

import discord

from bot.core.channels.migration import GuildInventory, InventoryChannel, ResourceKindName


def _channel_kind(channel: discord.abc.GuildChannel) -> ResourceKindName | None:
    if isinstance(channel, discord.CategoryChannel):
        return "category"
    if isinstance(channel, discord.TextChannel):
        if channel.is_news():
            return "announcement"
        return "text"
    return None


def gather_guild_inventory(guild: discord.Guild) -> GuildInventory:
    """Snapshot guild categories/text channels for migration matching."""
    items: list[InventoryChannel] = []
    channels: list[discord.abc.GuildChannel] = [
        *list(guild.categories),
        *list(guild.text_channels),
    ]
    for channel in channels:
        kind = _channel_kind(channel)
        if kind is None:
            continue
        parent_id = None if isinstance(channel, discord.CategoryChannel) else channel.category_id
        items.append(
            InventoryChannel(
                discord_id=channel.id,
                name=channel.name,
                kind=kind,
                parent_id=parent_id,
            )
        )
    rules = guild.rules_channel
    updates = guild.public_updates_channel
    return GuildInventory(
        channels=tuple(items),
        rules_channel_id=rules.id if isinstance(rules, discord.TextChannel) else None,
        public_updates_channel_id=(
            updates.id if isinstance(updates, discord.TextChannel) else None
        ),
    )
