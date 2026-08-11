from __future__ import annotations

import discord

from bot.constants import (
    DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    LEGACY_MODERATOR_ROLE_NAME,
)
from bot.core.channels.finder import ChannelLookupError, find_channel, require_channel
from bot.core.channels.layout.managed import hub_category_name, hub_channel_name
from bot.core.models.network import Network

__all__ = ["ChannelLookupError", "find_channel", "require_channel"]

# Canonical hub names derived from bot/layout/hub.yaml
CATEGORY_NETWORK = hub_category_name("network", fallback="The Network")
CATEGORY_MODERATION = hub_category_name("moderation", fallback="Moderation")
CATEGORY_LEADERS = hub_category_name("leaders", fallback="Leaders")

CHANNEL_RULES = hub_channel_name("rules", fallback="rules")
CHANNEL_JOIN_THE_NETWORK = hub_channel_name("join_the_network", fallback="join-the-network")
CHANNEL_LEADERS = hub_channel_name("leaders_channel", fallback="leaders-channel")
LEGACY_CHANNEL_LEADERS = "leaders"
CHANNEL_CHANGELOG = hub_channel_name("changelog", fallback="changelog")
CHANNEL_JOIN_REQUESTS = hub_channel_name("join_requests", fallback="join-requests")
CHANNEL_MODERATOR_ONLY = hub_channel_name("moderator_only", fallback="moderator-only")
CHANNEL_COMMANDS = hub_channel_name("commands", fallback="commands")
CHANNEL_NETWORK_ANNOUNCEMENTS = hub_channel_name(
    "network_announcements",
    fallback="network-announcements",
)

# Legacy names kept for cleanup/migration
CATEGORY_SUBSCRIBE = "Subscribe To Me!"
CHANNEL_WELCOME_SINK = "welcome-sink"


def join_channel_name(network_key: str) -> str:
    """Legacy per-network join channel name."""
    return f"join-{network_key.strip().lower()}"[:100]


def resolve_network_join_channel(
    guild: discord.Guild,
    network: Network,
) -> discord.TextChannel | None:
    if network.join_channel_id is not None:
        channel = guild.get_channel(network.join_channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel

    hub_category = resolve_network_hub_category(guild)
    return find_channel(
        guild,
        join_channel_name(network.key),
        channel_type=discord.TextChannel,
        category_id=hub_category.id if hub_category is not None else None,
    )


def resolve_category(guild: discord.Guild, display_name: str) -> discord.CategoryChannel | None:
    return find_channel(guild, display_name, channel_type=discord.CategoryChannel)


def resolve_network_hub_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    return resolve_category(guild, CATEGORY_NETWORK)


def resolve_moderation_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    return resolve_category(guild, CATEGORY_MODERATION)


def resolve_text_channel_in_category(
    guild: discord.Guild,
    *,
    name: str,
    category_id: int | None = None,
) -> discord.TextChannel | None:
    return find_channel(
        guild,
        name,
        channel_type=discord.TextChannel,
        category_id=category_id,
    )


def resolve_announcement_channel_in_category(
    guild: discord.Guild,
    *,
    name: str,
    category_id: int | None = None,
) -> discord.TextChannel | None:
    return find_channel(
        guild,
        name,
        channel_type=discord.TextChannel,
        category_id=category_id,
        predicate=lambda channel: isinstance(channel, discord.TextChannel)
        and channel.is_news(),
    )


def resolve_join_the_network_channel(guild: discord.Guild) -> discord.TextChannel | None:
    hub = resolve_network_hub_category(guild)
    if hub is not None:
        match = resolve_text_channel_in_category(
            guild,
            name=CHANNEL_JOIN_THE_NETWORK,
            category_id=hub.id,
        )
        if match is not None:
            return match
    return resolve_text_channel_in_category(guild, name=CHANNEL_JOIN_THE_NETWORK)


def resolve_leaders_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    return resolve_category(guild, CATEGORY_LEADERS)


def resolve_leaders_channel(guild: discord.Guild) -> discord.TextChannel | None:
    leaders_category = resolve_leaders_category(guild)
    if leaders_category is not None:
        match = find_channel(
            guild,
            (CHANNEL_LEADERS, LEGACY_CHANNEL_LEADERS),
            channel_type=discord.TextChannel,
            category_id=leaders_category.id,
        )
        if match is not None:
            return match

    hub = resolve_network_hub_category(guild)
    if hub is not None:
        match = find_channel(
            guild,
            (CHANNEL_LEADERS, LEGACY_CHANNEL_LEADERS),
            channel_type=discord.TextChannel,
            category_id=hub.id,
        )
        if match is not None:
            return match
    return find_channel(
        guild,
        (CHANNEL_LEADERS, LEGACY_CHANNEL_LEADERS),
        channel_type=discord.TextChannel,
    )


def resolve_changelog_channel(guild: discord.Guild) -> discord.TextChannel | None:
    leaders_category = resolve_leaders_category(guild)
    if leaders_category is None:
        return None
    return resolve_text_channel_in_category(
        guild,
        name=CHANNEL_CHANGELOG,
        category_id=leaders_category.id,
    )


def resolve_join_requests_channel(guild: discord.Guild) -> discord.TextChannel | None:
    mod_category = resolve_moderation_category(guild)
    if mod_category is not None:
        match = resolve_text_channel_in_category(
            guild,
            name=CHANNEL_JOIN_REQUESTS,
            category_id=mod_category.id,
        )
        if match is not None:
            return match
    return resolve_text_channel_in_category(guild, name=CHANNEL_JOIN_REQUESTS)


def resolve_network_admin_channel(guild: discord.Guild) -> discord.TextChannel | None:
    mod_category = resolve_moderation_category(guild)
    if mod_category is not None:
        match = resolve_text_channel_in_category(
            guild,
            name=CHANNEL_COMMANDS,
            category_id=mod_category.id,
        )
        if match is not None:
            return match
    return resolve_text_channel_in_category(guild, name=CHANNEL_COMMANDS)


def resolve_network_announcements_channel(
    guild: discord.Guild,
) -> discord.TextChannel | None:
    mod_category = resolve_moderation_category(guild)
    if mod_category is not None:
        match = find_network_announcements_text_channel(
            guild,
            category_id=mod_category.id,
            include_announcement=False,
        )
        if match is not None:
            return match
    return find_network_announcements_text_channel(
        guild,
        include_announcement=False,
    )


def find_network_announcements_text_channel(
    guild: discord.Guild,
    *,
    category_id: int | None = None,
    include_announcement: bool = True,
) -> discord.TextChannel | None:
    """Find #network-announcements regardless of announcement type (migration helper)."""
    return find_channel(
        guild,
        CHANNEL_NETWORK_ANNOUNCEMENTS,
        channel_type=discord.TextChannel,
        category_id=category_id,
        predicate=(
            None
            if include_announcement
            else lambda channel: isinstance(channel, discord.TextChannel)
            and not channel.is_news()
        ),
    )


def resolve_network_announcement_channel(
    guild: discord.Guild,
    network_key: str,
    *,
    category: discord.CategoryChannel | None = None,
) -> discord.abc.GuildChannel | None:
    """Legacy — network-wide announcement outputs are deprecated."""
    from bot.core.clients.names import announcement_channel_base_name

    return find_channel(
        guild,
        announcement_channel_base_name(network_key),
        channel_type=discord.TextChannel,
        category_id=category.id if category is not None else None,
        predicate=lambda channel: getattr(channel, "type", None)
        is discord.ChannelType.news,
    )


def resolve_welcome_sink_channel(guild: discord.Guild) -> discord.TextChannel | None:
    return find_channel(guild, CHANNEL_WELCOME_SINK, channel_type=discord.TextChannel)


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
