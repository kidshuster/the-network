from __future__ import annotations

import re

import discord

from bot.domain.client import Client
from bot.domain.errors import ProfileValidationError

_SLUG_RE = re.compile(r"[^a-z0-9]+")

LEGACY_CLIENT_PROFILE_CHANNEL = "network-profile"


def slugify_client_name(server_name: str) -> str:
    slug = _SLUG_RE.sub("-", server_name.strip().lower()).strip("-")
    return slug[:32] if slug else "server"


def build_unique_channel_name(guild: discord.Guild, base_name: str) -> str:
    existing = {
        channel.name.casefold() for channel in guild.channels if hasattr(channel, "name")
    }
    candidate = base_name[:100]
    if candidate.casefold() not in existing:
        return candidate
    for index in range(2, 100):
        suffix = f"-{index}"
        trimmed = base_name[: 100 - len(suffix)] + suffix
        if trimmed.casefold() not in existing:
            return trimmed
    raise ProfileValidationError("Could not allocate a unique channel name.")


def build_client_profile_channel_base(server_name: str) -> str:
    return f"{slugify_client_name(server_name)}-profile"[:100]


def build_client_publish_channel_base(server_name: str, network_key: str) -> str:
    slug = slugify_client_name(server_name)
    key = network_key.strip().lower()
    return f"{slug}-{key}-publish"[:100]


def build_client_subscribe_channel_base(server_name: str, network_key: str) -> str:
    slug = slugify_client_name(server_name)
    key = network_key.strip().lower()
    return f"{slug}-{key}-subscribe"[:100]


def legacy_publish_channel_name(network_key: str) -> str:
    return f"{network_key.strip().lower()}-publish"


def legacy_subscribe_channel_name(network_key: str) -> str:
    return f"{network_key.strip().lower()}-subscribe"


def publish_channel_name_candidates(server_name: str, network_key: str) -> tuple[str, ...]:
    return (
        build_client_publish_channel_base(server_name, network_key),
        legacy_publish_channel_name(network_key),
    )


def subscribe_channel_name_candidates(server_name: str, network_key: str) -> tuple[str, ...]:
    return (
        build_client_subscribe_channel_base(server_name, network_key),
        legacy_subscribe_channel_name(network_key),
    )


def profile_channel_name_candidates(server_name: str) -> tuple[str, ...]:
    return (
        build_client_profile_channel_base(server_name),
        LEGACY_CLIENT_PROFILE_CHANNEL,
    )


def build_network_channel_name(
    guild: discord.Guild,
    network_key: str,
    suffix: str,
) -> str:
    key = network_key.strip().lower()
    cleaned_suffix = suffix.strip().lower()
    return build_unique_channel_name(guild, f"{key}-{cleaned_suffix}")


def announcement_channel_base_name(network_key: str) -> str:
    key = network_key.strip().lower()
    return f"{key}-announcements"[:100]


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
