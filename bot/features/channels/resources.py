"""Public feature channel/category resource API (Architecture Contract Phase 7).

This module is the only production boundary for hub channel/category lookup.
Display names come from feature layout YAML; lookup uses generic core finders.
"""

from __future__ import annotations

import discord

from bot.core.channels.finder import find_channel as core_find_channel
from bot.features.channels.layout.managed import (
    hub_category_aliases,
    hub_category_name,
    hub_channel_aliases,
    hub_channel_name,
)

# Stable feature resource IDs. Display names come from YAML.
NETWORK = "network"
MODERATION = "moderation"
LEADERS = "leaders"

RULES = "rules"
JOIN_THE_NETWORK = "join_the_network"
LEADERS_CHANNEL = "leaders_channel"
CHANGELOG = "changelog"
JOIN_REQUESTS = "join_requests"
ADMIN = "admin"
NETWORK_ANNOUNCEMENTS = "network_announcements"

# Backward-compatible constant names used across the feature tree.
HUB_CATEGORY_NETWORK = NETWORK
HUB_CATEGORY_MODERATION = MODERATION
HUB_CATEGORY_LEADERS = LEADERS
HUB_CHANNEL_RULES = RULES
HUB_CHANNEL_JOIN_THE_NETWORK = JOIN_THE_NETWORK
HUB_CHANNEL_LEADERS = LEADERS_CHANNEL
HUB_CHANNEL_CHANGELOG = CHANGELOG
HUB_CHANNEL_JOIN_REQUESTS = JOIN_REQUESTS
HUB_CHANNEL_ADMIN = ADMIN
HUB_CHANNEL_NETWORK_ANNOUNCEMENTS = NETWORK_ANNOUNCEMENTS

# Display-name snapshots from layout YAML (prefer name(resource_id) for new code).
CATEGORY_NETWORK = hub_category_name(NETWORK)
CATEGORY_MODERATION = hub_category_name(MODERATION)
CATEGORY_LEADERS = hub_category_name(LEADERS)
CHANNEL_RULES = hub_channel_name(RULES)
CHANNEL_JOIN_THE_NETWORK = hub_channel_name(JOIN_THE_NETWORK)
CHANNEL_LEADERS = hub_channel_name(LEADERS_CHANNEL)
CHANNEL_CHANGELOG = hub_channel_name(CHANGELOG)
CHANNEL_JOIN_REQUESTS = hub_channel_name(JOIN_REQUESTS)
CHANNEL_ADMIN = hub_channel_name(ADMIN)
CHANNEL_NETWORK_ANNOUNCEMENTS = hub_channel_name(NETWORK_ANNOUNCEMENTS)


class ResourceLookupError(LookupError):
    """Required feature resource was not found in the guild."""

    def __init__(self, resource_id: str, *, kind: str) -> None:
        self.resource_id = resource_id
        self.kind = kind
        super().__init__(f"Required {kind} resource {resource_id!r} was not found.")


def name(resource_id: str) -> str:
    """Return the configured display name for a channel or category resource ID."""
    try:
        return hub_channel_name(resource_id)
    except KeyError:
        return hub_category_name(resource_id)


def find_category(guild: discord.Guild, resource_id: str) -> discord.CategoryChannel | None:
    return core_find_channel(
        guild,
        hub_category_aliases(resource_id),
        channel_type=discord.CategoryChannel,
    )


def require_category(guild: discord.Guild, resource_id: str) -> discord.CategoryChannel:
    category = find_category(guild, resource_id)
    if category is None:
        raise ResourceLookupError(resource_id, kind="category")
    return category


def find_channel(
    guild: discord.Guild,
    resource_id: str,
    *,
    category_id: int | None = None,
    include_announcement: bool = True,
) -> discord.TextChannel | None:
    return core_find_channel(
        guild,
        hub_channel_aliases(resource_id),
        channel_type=discord.TextChannel,
        category_id=category_id,
        predicate=(
            None
            if include_announcement
            else lambda channel: isinstance(channel, discord.TextChannel)
            and not channel.is_news()
        ),
    )


def require_channel(
    guild: discord.Guild,
    resource_id: str,
    *,
    category_id: int | None = None,
) -> discord.TextChannel:
    channel = find_channel(guild, resource_id, category_id=category_id)
    if channel is None:
        raise ResourceLookupError(resource_id, kind="channel")
    return channel


# --- Convenience resolvers (category-scoped hub lookups) -------------------


def find_network_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    return find_category(guild, NETWORK)


def find_moderation_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    return find_category(guild, MODERATION)


def find_leaders_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    return find_category(guild, LEADERS)


def find_join_the_network_channel(guild: discord.Guild) -> discord.TextChannel | None:
    hub = find_network_category(guild)
    if hub is not None:
        match = find_channel(guild, JOIN_THE_NETWORK, category_id=hub.id)
        if match is not None:
            return match
    return find_channel(guild, JOIN_THE_NETWORK)


def find_leaders_channel(guild: discord.Guild) -> discord.TextChannel | None:
    leaders_category = find_leaders_category(guild)
    if leaders_category is not None:
        match = find_channel(guild, LEADERS_CHANNEL, category_id=leaders_category.id)
        if match is not None:
            return match

    hub = find_network_category(guild)
    if hub is not None:
        match = find_channel(guild, LEADERS_CHANNEL, category_id=hub.id)
        if match is not None:
            return match
    return find_channel(guild, LEADERS_CHANNEL)


def find_changelog_channel(guild: discord.Guild) -> discord.TextChannel | None:
    leaders_category = find_leaders_category(guild)
    if leaders_category is None:
        return None
    return find_channel(guild, CHANGELOG, category_id=leaders_category.id)


def find_join_requests_channel(guild: discord.Guild) -> discord.TextChannel | None:
    mod_category = find_moderation_category(guild)
    if mod_category is not None:
        match = find_channel(guild, JOIN_REQUESTS, category_id=mod_category.id)
        if match is not None:
            return match
    return find_channel(guild, JOIN_REQUESTS)


def find_admin_channel(guild: discord.Guild) -> discord.TextChannel | None:
    community = guild.public_updates_channel
    if isinstance(community, discord.TextChannel):
        return community
    mod_category = find_moderation_category(guild)
    if mod_category is not None:
        match = find_channel(guild, ADMIN, category_id=mod_category.id)
        if match is not None:
            return match
    return find_channel(guild, ADMIN)


def find_network_announcements_channel(
    guild: discord.Guild,
) -> discord.TextChannel | None:
    category = find_moderation_category(guild)
    return find_channel(
        guild,
        NETWORK_ANNOUNCEMENTS,
        category_id=category.id if category is not None else None,
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
        NETWORK_ANNOUNCEMENTS,
        category_id=category_id,
        include_announcement=include_announcement,
    )


# Legacy aliases kept for call-site clarity during migration reviews.
resolve_hub_category = find_category
resolve_hub_channel = find_channel
resolve_network_hub_category = find_network_category
resolve_moderation_category = find_moderation_category
resolve_leaders_category = find_leaders_category
resolve_join_the_network_channel = find_join_the_network_channel
resolve_leaders_channel = find_leaders_channel
resolve_changelog_channel = find_changelog_channel
resolve_join_requests_channel = find_join_requests_channel
resolve_network_admin_channel = find_admin_channel
resolve_network_announcements_channel = find_network_announcements_channel
