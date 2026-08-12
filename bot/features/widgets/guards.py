from __future__ import annotations

from typing import Any, cast

import discord

from bot.core.templates import render_text
from bot.errors import UserFacingError


def _is_guild_member(user: discord.abc.User) -> bool:
    return isinstance(user, discord.Member) or (
        hasattr(user, "roles") and hasattr(user, "guild_permissions")
    )

def require_hub_guild(bot: Any, guild: discord.Guild | None) -> discord.Guild:
    if guild is None or guild.id != bot.settings.guild_id:
        raise UserFacingError(render_text("hub_guild_only"), code="hub_guild_only")
    if bot.bot_context is None:
        raise UserFacingError(render_text("bot_not_ready"), code="bot_not_ready")
    return guild

def require_manage_guild(member: discord.abc.User) -> None:
    if not _is_guild_member(member):
        raise UserFacingError(render_text("manage_guild_required"), code="manage_guild_required")
    perms = cast(Any, member).guild_permissions
    if not perms.manage_guild:
        raise UserFacingError(render_text("manage_guild_required"), code="manage_guild_required")

def require_client_member(
    guild: discord.Guild,
    member: discord.abc.User,
    client: Any,
    *,
    popup: str = "client_role_required_edit",
    allow_non_member: bool = False,
) -> None:
    if not _is_guild_member(member):
        if allow_non_member:
            return
        raise UserFacingError(render_text("invalid_member"), code="invalid_member")
    typed = cast(Any, member)
    role = guild.get_role(client.client_role_id)
    if role is None or (role not in typed.roles and not typed.guild_permissions.manage_guild):
        raise UserFacingError(render_text(popup), code="client_role_required")
