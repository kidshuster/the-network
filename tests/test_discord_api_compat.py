from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.services.guild_permissions import create_text_channel_with_overwrites


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
        return MagicMock(spec=discord.TextChannel)

    guild.create_text_channel = strict_create

    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10
    bot_member.top_role.id = 50

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 100

    with patch(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        new=AsyncMock(),
    ):
        await create_text_channel_with_overwrites(
            guild,
            bot_member,
            name="network-profile-probe",
            category=category,
            overwrites={everyone: discord.PermissionOverwrite(view_channel=False)},
            reason="test",
        )
