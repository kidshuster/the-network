from __future__ import annotations

from dataclasses import dataclass

import discord

from bot.constants import DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME
from bot.layout.schema import TargetKind


@dataclass(frozen=True)
class LayoutContext:
    guild: discord.Guild
    bot_member: discord.Member
    access_role: discord.Role | None = None
    moderator_role: discord.Role | None = None
    operator_role: discord.Role | None = None
    bot_access_role: discord.Role | None = None
    client_role: discord.Role | None = None
    client_roles: tuple[discord.Role, ...] = ()
    server_name: str | None = None
    slug: str | None = None
    network_key: str | None = None
    reason: str = "The Network layout sync"


class LayoutRoleError(ValueError):
    pass


def resolve_targets(
    context: LayoutContext,
    target: TargetKind,
) -> tuple[discord.Role, ...]:
    if target == "everyone":
        return (context.guild.default_role,)
    if target == "network_access":
        role = context.access_role
    elif target == "moderator":
        role = context.moderator_role
    elif target == "bot_access":
        role = context.bot_access_role
        if role is None and isinstance(context.guild.roles, (list, tuple)):
            role = next(
                (
                    item
                    for item in context.guild.roles
                    if item.name == DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME
                ),
                None,
            )
    elif target == "current_client_role":
        role = context.client_role
    else:
        return context.client_roles
    return (role,) if role is not None else ()


def validate_target(
    context: LayoutContext,
    logical_name: str,
    target: TargetKind,
    roles: tuple[discord.Role, ...],
) -> None:
    optional = target in {
        "moderator",
        "bot_access",
        "current_client_role",
        "client_roles",
    }
    if not roles and not optional:
        raise LayoutRoleError(f"{logical_name}: required role {target!r} is unavailable")
    for role in roles:
        if role.is_default() is True:
            continue
        if role.managed is True:
            raise LayoutRoleError(f"{logical_name}: role {role.name!r} is Discord-managed")
        if (
            isinstance(role.position, int)
            and isinstance(context.bot_member.top_role.position, int)
            and role.position >= context.bot_member.top_role.position
        ):
            raise LayoutRoleError(
                f"{logical_name}: role {role.name!r} is not below the bot's top role",
            )
