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


def require_actor(user: discord.abc.User | None) -> discord.abc.User:
    if user is None or not _is_guild_member(user):
        raise UserFacingError(render_text("invalid_member"), code="invalid_member")
    return user


def require_manage_guild(member: discord.abc.User) -> None:
    actor = require_actor(member)
    perms = cast(Any, actor).guild_permissions
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


def interaction_guild(bot: Any, interaction: discord.Interaction) -> discord.Guild:
    return require_hub_guild(bot, interaction.guild)


def interaction_actor(interaction: discord.Interaction) -> discord.abc.User:
    return require_actor(interaction.user)


def interaction_bot_member(guild: discord.Guild) -> discord.Member:
    me = guild.me
    if me is None:
        raise UserFacingError(render_text("bot_not_ready"), code="bot_not_ready")
    return me


def interaction_view_registry(interaction: discord.Interaction) -> Any:
    return interaction.client.make_view_registry()  # type: ignore[attr-defined]