from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord


def http_50013(message: str = "Missing Permissions") -> discord.HTTPException:
    exc = discord.HTTPException(MagicMock(), message)
    exc.status = 403
    exc.code = 50013
    return exc


def make_role(
    *,
    name: str,
    role_id: int,
    position: int,
    is_default: bool = False,
    managed: bool = False,
) -> MagicMock:
    role = MagicMock(spec=discord.Role, name=name, id=role_id, position=position)
    role.name = name
    role.is_default.return_value = is_default
    role.managed = managed
    return role


def make_bot_member(
    *,
    access: MagicMock,
    operator: MagicMock,
    bot_id: int = 999,
) -> MagicMock:
    from unittest.mock import PropertyMock

    bot = MagicMock(spec=discord.Member, id=bot_id, roles=[access, operator])
    bot.top_role = operator
    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = True
    perms.manage_webhooks = True
    perms.manage_guild = True
    perms.administrator = False
    type(bot).guild_permissions = PropertyMock(return_value=perms)
    return bot


def make_guild_with_roles(
    *,
    access_position: int = 10,
    operator_position: int = 11,
    human_mod_position: int = 4,
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    guild.categories = []
    guild.text_channels = []
    guild.channels = []
    guild.rules_channel = None
    guild.default_notifications = discord.NotificationLevel.only_mentions

    everyone = make_role(name="@everyone", role_id=1, position=0, is_default=True)
    guild.default_role = everyone

    human_mod = make_role(name="Moderator", role_id=30, position=human_mod_position)
    access_role = make_role(name="The Network", role_id=40, position=access_position)
    bot_access_role = make_role(
        name="The Network Bot Access",
        role_id=45,
        position=min(access_position + 1, operator_position - 1),
    )
    operator_role = make_role(name="The Network+", role_id=50, position=operator_position)
    operator_role.permissions.manage_channels = True
    operator_role.permissions.manage_roles = True
    operator_role.permissions.manage_webhooks = True
    operator_role.permissions.send_messages = True
    operator_role.permissions.embed_links = True
    operator_role.permissions.attach_files = True
    operator_role.permissions.read_message_history = True
    operator_role.permissions.manage_messages = True
    operator_role.permissions.manage_emojis_and_stickers = True

    bot = make_bot_member(access=access_role, operator=operator_role)
    bot.roles = [access_role, bot_access_role, operator_role]
    guild.roles = [everyone, human_mod, access_role, bot_access_role, operator_role]
    guild.me = bot
    return guild, bot, human_mod, access_role, operator_role


def discord_like_create_text_channel(
    bot_member: discord.Member,
    *,
    on_create: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Reject channel creates whose overwrites target roles the bot cannot configure."""

    async def _create(**kwargs: object) -> discord.TextChannel:
        overwrites = kwargs.get("overwrites") or {}
        top = bot_member.top_role
        for target, _overwrite in overwrites.items():
            if isinstance(target, discord.Member):
                raise http_50013("Cannot set member overwrites on channel create")
            if isinstance(target, discord.Role) and not target.is_default():
                if getattr(target, "managed", False):
                    raise http_50013("Cannot set overwrites on managed role")
                if target.id != top.id and top.position <= target.position:
                    raise http_50013("Role hierarchy prevents overwrite")
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 9001
        channel.name = str(kwargs.get("name", "channel"))
        channel.category_id = getattr(kwargs.get("category"), "id", None)
        channel.edit = AsyncMock()
        channel.delete = AsyncMock()
        if on_create is not None:
            on_create(**kwargs)
        return channel

    return _create


def discord_like_hub_category_create_text_channel(
    bot_member: discord.Member,
    *,
    on_create: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Simulate Discord rejecting overwrites-at-create inside a permissioned category (50013)."""
    base = discord_like_create_text_channel(bot_member, on_create=on_create)

    async def _create(**kwargs: object) -> discord.TextChannel:
        category = kwargs.get("category")
        overwrites = kwargs.get("overwrites") or {}
        if category is not None and overwrites:
            raise http_50013(
                "Missing Permissions — channel overwrites at create time inside "
                "a permissioned category"
            )
        return await base(**kwargs)

    return _create
