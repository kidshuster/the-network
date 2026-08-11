"""Public feature channel/category resource API (Architecture Contract Phase 7)."""

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
