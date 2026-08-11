from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.core.permissions.service import build_context, permission_service


def _create_text_channel_param_names() -> set[str]:
    return set(inspect.signature(discord.Guild.create_text_channel).parameters)


async def test_create_text_channel_with_overwrites_uses_only_discord_py_kwargs() -> None:
    """Guard against passing kwargs discord.py rejects (e.g. sync_permissions on create)."""
    allowed = _create_text_channel_param_names()
    guild = MagicMock(spec=discord.Guild)

    async def strict_create(**kwargs: object) -> discord.TextChannel:
        unknown = set(kwargs) - allowed
        if unknown:
            name = next(iter(sorted(unknown)))
            msg = f"Guild.create_text_channel() got an unexpected keyword argument {name!r}"
            raise TypeError(msg)
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 1
        channel.category_id = 100
        channel.overwrites = {}
        channel.edit = AsyncMock()
        return channel

    guild.create_text_channel = strict_create

    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild = guild
    bot_member.guild_permissions.manage_channels = True
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10
    bot_member.top_role.id = 50
    bot_access = MagicMock(spec=discord.Role)
    bot_access.id = 45
    bot_access.name = "The Network Bot Access"
    bot_access.position = 9
    bot_access.managed = False
    bot_access.is_default.return_value = False

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 100

    with patch(
        "bot.features.hub.notifications.ensure_guild_only_mention_notifications",
        new=AsyncMock(),
    ):
        await permission_service.ensure_text_channel(
            guild,
            build_context(
                guild,
                bot_member,
                access_role=None,
                moderator_role=None,
                operator_role=bot_access,
            ),
            existing=None,
            name="network-profile-probe",
            category=category,
            overwrites={everyone: discord.PermissionOverwrite(view_channel=False)},
            managed_targets={everyone, bot_access},
            reason="test",
        )
