from __future__ import annotations

import discord

from bot.domain.errors import ProfileValidationError


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
