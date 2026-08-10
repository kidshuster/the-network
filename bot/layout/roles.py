from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import discord

from bot.layout.schema import ClientScope, OverwriteBindingSpec, RoleKey
from bot.permissions.service import can_configure_role


@dataclass(frozen=True)
class LayoutContext:
    guild: discord.Guild
    bot_member: discord.Member
    access_role: discord.Role | None = None
    moderator_role: discord.Role | None = None
    operator_role: discord.Role | None = None
    client_role: discord.Role | None = None
    client_roles: tuple[discord.Role, ...] = ()
    server_name: str | None = None
    slug: str | None = None
    network_key: str | None = None
    reason: str = "The Network layout sync"


def resolve_static_role(
    context: LayoutContext,
    key: RoleKey,
) -> discord.Role | discord.Member | None:
    if key == "everyone":
        return context.guild.default_role
    if key == "access":
        return context.access_role
    if key == "operator":
        return context.operator_role
    if key == "moderator":
        return context.moderator_role
    if key == "bot":
        return context.bot_member
    return None


def expand_client_roles(
    context: LayoutContext,
    scope: ClientScope,
) -> tuple[discord.Role, ...]:
    if scope == "this_client":
        if context.client_role is None:
            return ()
        return (context.client_role,)
    return context.client_roles


def resolve_binding_targets(
    context: LayoutContext,
    binding: OverwriteBindingSpec,
) -> list[discord.Role | discord.Member]:
    if binding.role == "client":
        assert binding.scope is not None
        return list(expand_client_roles(context, binding.scope))
    target = resolve_static_role(context, binding.role)
    if target is None:
        return []
    return [target]


def role_is_applicable(
    context: LayoutContext,
    target: discord.Role | discord.Member,
) -> bool:
    if isinstance(target, discord.Member):
        return True
    if target.is_default():
        return True
    if context.operator_role is not None and target.id == context.operator_role.id:
        return True
    if context.access_role is not None and target.id == context.access_role.id:
        return True
    return can_configure_role(context.bot_member, target)


def iter_named_roles(roles: Iterable[discord.Role]) -> tuple[discord.Role, ...]:
    return tuple(roles)
