from __future__ import annotations

import re

import discord

from bot.core.models.client import Client
from bot.core.models.errors import ProfileValidationError

_SLUG_RE = re.compile(r"[^a-z0-9]+")

CHANNEL_PREFIX_PROFILE = "📚-"
CHANNEL_PREFIX_PUBLISH = "📤-"
CHANNEL_PREFIX_NETWORK = "🌐-"
CHANNEL_PREFIX_ANNOUNCEMENTS = "📢-"


def slugify_client_name(server_name: str) -> str:
    slug = _SLUG_RE.sub("-", server_name.strip().lower()).strip("-")
    return slug[:32] if slug else "server"


def build_client_role_name(server_name: str) -> str:
    return f"Client: {server_name.strip()}"[:100]


def build_unique_channel_name(guild: discord.Guild, base_name: str) -> str:
    existing = {channel.name.casefold() for channel in guild.channels if hasattr(channel, "name")}
    candidate = base_name[:100]
    if candidate.casefold() not in existing:
        return candidate
    for index in range(2, 100):
        suffix = f"-{index}"
        trimmed = base_name[: 100 - len(suffix)] + suffix
        if trimmed.casefold() not in existing:
            return trimmed
    raise ProfileValidationError("Could not allocate a unique channel name.")


def _legacy_unprefixed(base_name: str, prefix: str) -> str | None:
    if base_name.startswith(prefix):
        return base_name[len(prefix) :]
    return None


def build_client_profile_channel_base(server_name: str) -> str:
    return f"{CHANNEL_PREFIX_PROFILE}{slugify_client_name(server_name)}-profile"[:100]


def build_client_publish_channel_base(server_name: str, network_key: str) -> str:
    slug = slugify_client_name(server_name)
    key = network_key.strip().lower()
    return f"{CHANNEL_PREFIX_PUBLISH}{slug}-{key}-publish"[:100]


def build_client_subscribe_channel_base(server_name: str, network_key: str) -> str:
    slug = slugify_client_name(server_name)
    key = network_key.strip().lower()
    return f"{CHANNEL_PREFIX_NETWORK}{slug}-{key}-subscribe"[:100]


def build_client_announcements_channel_base(server_name: str, network_key: str) -> str:
    slug = slugify_client_name(server_name)
    key = network_key.strip().lower()
    return f"{CHANNEL_PREFIX_ANNOUNCEMENTS}{slug}-{key}-announcements"[:100]


def client_profile_channel_name_candidates(server_name: str) -> tuple[str, ...]:
    current = build_client_profile_channel_base(server_name)
    legacy = _legacy_unprefixed(current, CHANNEL_PREFIX_PROFILE)
    return (current, legacy) if legacy else (current,)


def client_publish_channel_name_candidates(
    server_name: str,
    network_key: str,
) -> tuple[str, ...]:
    current = build_client_publish_channel_base(server_name, network_key)
    slug = slugify_client_name(server_name)
    key = network_key.strip().lower()
    stem = f"{slug}-{key}-publish"
    # Prior 🌐- prefix, then unprefixed product names.
    prior_network = f"{CHANNEL_PREFIX_NETWORK}{stem}"
    candidates = [current]
    for name in (prior_network, stem):
        if name not in candidates:
            candidates.append(name)
    return tuple(candidates)


def client_subscribe_channel_name_candidates(
    server_name: str,
    network_key: str,
) -> tuple[str, ...]:
    current = build_client_subscribe_channel_base(server_name, network_key)
    legacy = _legacy_unprefixed(current, CHANNEL_PREFIX_NETWORK)
    return (current, legacy) if legacy else (current,)


def client_announcements_channel_name_candidates(
    server_name: str,
    network_key: str,
) -> tuple[str, ...]:
    current = build_client_announcements_channel_base(server_name, network_key)
    legacy = _legacy_unprefixed(current, CHANNEL_PREFIX_ANNOUNCEMENTS)
    return (current, legacy) if legacy else (current,)


def build_network_channel_name(
    guild: discord.Guild,
    network_key: str,
    suffix: str,
) -> str:
    key = network_key.strip().lower()
    cleaned_suffix = suffix.strip().lower()
    return build_unique_channel_name(guild, f"{key}-{cleaned_suffix}")


def build_client_profile_channel_name(guild: discord.Guild, client: Client) -> str:
    return build_unique_channel_name(
        guild,
        build_client_profile_channel_base(client.server_name),
    )


def build_client_publish_channel_name(
    guild: discord.Guild,
    client: Client,
    network_key: str,
) -> str:
    return build_unique_channel_name(
        guild,
        build_client_publish_channel_base(client.server_name, network_key),
    )


def build_client_subscribe_channel_name(
    guild: discord.Guild,
    client: Client,
    network_key: str,
) -> str:
    return build_unique_channel_name(
        guild,
        build_client_subscribe_channel_base(client.server_name, network_key),
    )


def build_client_announcements_channel_name(
    guild: discord.Guild,
    client: Client,
    network_key: str,
) -> str:
    return build_unique_channel_name(
        guild,
        build_client_announcements_channel_base(client.server_name, network_key),
    )
