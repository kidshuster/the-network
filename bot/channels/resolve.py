from __future__ import annotations

import discord

from bot.channels.layout.managed import hub_category_aliases, hub_channel_aliases
from bot.constants import (
    DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    LEGACY_MODERATOR_ROLE_NAME,
)
from bot.core.models.network import Network

# Stable layout.yaml resource IDs. Display names come from YAML `name` / `legacy_names`.
HUB_CATEGORY_NETWORK = "network"
HUB_CATEGORY_MODERATION = "moderation"
HUB_CATEGORY_LEADERS = "leaders"

HUB_CHANNEL_RULES = "rules"
HUB_CHANNEL_JOIN_THE_NETWORK = "join_the_network"
HUB_CHANNEL_LEADERS = "leaders_channel"
HUB_CHANNEL_CHANGELOG = "changelog"
HUB_CHANNEL_JOIN_REQUESTS = "join_requests"
HUB_CHANNEL_MODERATOR_ONLY = "moderator_only"
HUB_CHANNEL_COMMANDS = "commands"
HUB_CHANNEL_NETWORK_ANNOUNCEMENTS = "network_announcements"

# Legacy names kept for cleanup/migration of pre-layout resources
CATEGORY_SUBSCRIBE = "Subscribe To Me!"
CHANNEL_WELCOME_SINK = "welcome-sink"


def join_channel_name(network_key: str) -> str:
    """Legacy per-network join channel name."""
    return f"join-{network_key.strip().lower()}"[:100]


def _name_matches(channel_name: str, aliases: tuple[str, ...]) -> bool:
    target = channel_name.casefold()
    return any(alias.casefold() == target for alias in aliases)


def resolve_hub_category(
    guild: discord.Guild,
    category_id: str,
) -> discord.CategoryChannel | None:
    """Resolve a hub category by layout.yaml resource ID."""
    aliases = hub_category_aliases(category_id)
    for channel in guild.categories:
        if _name_matches(channel.name, aliases):
            return channel
    return None


def resolve_hub_channel(
    guild: discord.Guild,
    channel_id: str,
    *,
    category_id: int | None = None,
    include_announcement: bool = True,
) -> discord.TextChannel | None:
    """Resolve a hub text channel by layout.yaml resource ID.

    Matches the current YAML ``name`` and any ``legacy_names``. When
    ``include_announcement`` is False, news channels are skipped (used while
    migrating hub announcements to regular text).
    """
    aliases = hub_channel_aliases(channel_id)
    for channel in guild.text_channels:
        if category_id is not None and channel.category_id != category_id:
            continue
        if not _name_matches(channel.name, aliases):
            continue
        if not include_announcement and channel.is_news():
            continue
        return channel
    return None


def resolve_category(guild: discord.Guild, display_name: str) -> discord.CategoryChannel | None:
    target = display_name.casefold()
    for channel in guild.categories:
        if channel.name.casefold() == target:
            return channel
    return None


def resolve_text_channel_in_category(
    guild: discord.Guild,
    *,
    name: str,
    category_id: int | None = None,
) -> discord.TextChannel | None:
    target = name.casefold()
    for channel in guild.text_channels:
        if channel.name.casefold() != target:
            continue
        if category_id is not None and channel.category_id != category_id:
            continue
        return channel
    return None


def resolve_announcement_channel_in_category(
    guild: discord.Guild,
    *,
    name: str,
    category_id: int | None = None,
) -> discord.TextChannel | None:
    target = name.casefold()
    for channel in guild.text_channels:
        if not channel.is_news():
            continue
        if channel.name.casefold() != target:
            continue
        if category_id is not None and channel.category_id != category_id:
            continue
        return channel
    return None


def resolve_network_join_channel(
    guild: discord.Guild,
    network: Network,
) -> discord.TextChannel | None:
    if network.join_channel_id is not None:
        channel = guild.get_channel(network.join_channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel

    expected_name = join_channel_name(network.key).casefold()
    hub_category = resolve_hub_category(guild, HUB_CATEGORY_NETWORK)
    for channel in guild.text_channels:
        if channel.name.casefold() != expected_name:
            continue
        if hub_category is not None and channel.category_id != hub_category.id:
            continue
        return channel
    return None


def resolve_network_announcement_channel(
    guild: discord.Guild,
    network_key: str,
    *,
    category: discord.CategoryChannel | None = None,
) -> discord.abc.GuildChannel | None:
    """Legacy — network-wide announcement outputs are deprecated."""
    from bot.core.clients.names import announcement_channel_base_name

    target = announcement_channel_base_name(network_key).casefold()
    for channel in guild.channels:
        if getattr(channel, "type", None) is not discord.ChannelType.news:
            continue
        if channel.name.casefold() != target:
            continue
        if category is not None and channel.category_id != category.id:
            continue
        return channel
    return None


def resolve_welcome_sink_channel(guild: discord.Guild) -> discord.TextChannel | None:
    target = CHANNEL_WELCOME_SINK.casefold()
    for channel in guild.text_channels:
        if channel.name.casefold() == target:
            return channel
    return None


def resolve_subscribe_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    """Legacy Subscribe To Me! category."""
    return resolve_category(guild, CATEGORY_SUBSCRIBE)


def iter_subscribe_announcement_channels(
    guild: discord.Guild,
    category: discord.CategoryChannel,
) -> list[discord.abc.GuildChannel]:
    channels: list[discord.abc.GuildChannel] = []
    for channel in guild.channels:
        if channel.category_id != category.id:
            continue
        if getattr(channel, "type", None) is not discord.ChannelType.news:
            continue
        channels.append(channel)
    return channels


def resolve_human_moderator_role(
    guild: discord.Guild,
    *,
    role_name: str | None = None,
) -> discord.Role | None:
    candidates = [role_name] if role_name else []
    candidates.append(LEGACY_MODERATOR_ROLE_NAME)
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        role = discord.utils.get(guild.roles, name=candidate)
        if role is not None:
            return role
    return None


def resolve_access_role(
    guild: discord.Guild,
    *,
    role_name: str | None = None,
) -> discord.Role | None:
    target = (role_name or DEFAULT_NETWORK_ACCESS_ROLE_NAME).strip()
    if not target:
        return None
    return discord.utils.get(guild.roles, name=target)


def resolve_operator_role(
    guild: discord.Guild,
    *,
    role_name: str | None = None,
) -> discord.Role | None:
    target = (role_name or DEFAULT_NETWORK_OPERATOR_ROLE_NAME).strip()
    if not target:
        return None
    return discord.utils.get(guild.roles, name=target)


def resolve_bot_role(
    guild: discord.Guild,
    *,
    role_name: str | None = None,
) -> discord.Role | None:
    return resolve_access_role(guild, role_name=role_name)


def resolve_moderator_role(
    guild: discord.Guild,
    *,
    role_name: str | None = None,
) -> discord.Role | None:
    return resolve_bot_role(guild, role_name=role_name)
