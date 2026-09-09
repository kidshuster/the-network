"""Feature role lookup helpers (moderator / access naming known to The Network)."""

from __future__ import annotations

import discord

from bot.constants import (
    DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    LEGACY_MODERATOR_ROLE_NAME,
)


def find_human_moderator_role(
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


def find_access_role(
    guild: discord.Guild,
    *,
    role_name: str | None = None,
) -> discord.Role | None:
    target = (role_name or DEFAULT_NETWORK_ACCESS_ROLE_NAME).strip()
    if not target:
        return None
    return discord.utils.get(guild.roles, name=target)


def find_operator_role(
    guild: discord.Guild,
    *,
    role_name: str | None = None,
) -> discord.Role | None:
    target = (role_name or DEFAULT_NETWORK_OPERATOR_ROLE_NAME).strip()
    if not target:
        return None
    return discord.utils.get(guild.roles, name=target)


# Legacy aliases.
resolve_human_moderator_role = find_human_moderator_role
resolve_access_role = find_access_role
resolve_operator_role = find_operator_role
resolve_bot_role = find_access_role
resolve_moderator_role = find_access_role
