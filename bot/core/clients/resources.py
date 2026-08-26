from __future__ import annotations

from dataclasses import dataclass

import discord

from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription


async def fetch_guild_channel(
    guild: discord.Guild,
    channel_id: int,
) -> discord.abc.GuildChannel | None:
    channel = guild.get_channel(channel_id)
    if channel is not None:
        return channel
    try:
        fetched = await guild.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden):
        return None
    return fetched if isinstance(fetched, discord.abc.GuildChannel) else None


async def fetch_client_role(
    guild: discord.Guild,
    client: Client,
) -> discord.Role | None:
    role = guild.get_role(client.client_role_id)
    if role is not None:
        return role
    try:
        return await guild.fetch_role(client.client_role_id)
    except (discord.NotFound, discord.Forbidden):
        return None


async def resolve_client_category(
    guild: discord.Guild,
    client: Client,
) -> discord.CategoryChannel | None:
    channel = await fetch_guild_channel(guild, client.category_id)
    return channel if isinstance(channel, discord.CategoryChannel) else None


async def resolve_client_profile_channel(
    guild: discord.Guild,
    client: Client,
) -> discord.TextChannel | None:
    channel = await fetch_guild_channel(guild, client.profile_channel_id)
    return channel if isinstance(channel, discord.TextChannel) else None


async def fetch_publish_channel(
    guild: discord.Guild,
    subscription: ClientSubscription,
) -> discord.TextChannel | None:
    if not subscription.publish_channel_id:
        return None
    channel = await fetch_guild_channel(guild, subscription.publish_channel_id)
    return channel if isinstance(channel, discord.TextChannel) else None


async def fetch_subscribe_channel(
    guild: discord.Guild,
    subscription: ClientSubscription,
) -> discord.abc.GuildChannel | None:
    return await fetch_guild_channel(guild, subscription.subscribe_channel_id)


async def fetch_announcements_channel(
    guild: discord.Guild,
    subscription: ClientSubscription,
) -> discord.TextChannel | None:
    if not subscription.announcements_channel_id:
        return None
    channel = await fetch_guild_channel(guild, subscription.announcements_channel_id)
    return channel if isinstance(channel, discord.TextChannel) else None


@dataclass(frozen=True)
class ClientResources:
    role: discord.Role | None
    category: discord.CategoryChannel | None
    profile_channel: discord.TextChannel | None


async def resolve_client_resources(
    guild: discord.Guild,
    client: Client,
) -> ClientResources:
    role = await fetch_client_role(guild, client)
    category = await resolve_client_category(guild, client)
    profile_channel = await resolve_client_profile_channel(guild, client)
    return ClientResources(
        role=role,
        category=category,
        profile_channel=profile_channel,
    )
