from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.services.guild_permissions import (
    build_commands_channel_overwrites,
    build_moderation_staff_overwrites,
    build_subscribe_announcement_channel_overwrites,
)


def test_moderation_channels_deny_everyone_and_access() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    guild.default_role = everyone
    access = MagicMock(spec=discord.Role, position=2)
    human_mod = MagicMock(spec=discord.Role, position=3, id=99)
    bot = MagicMock(spec=discord.Member)
    bot.top_role = MagicMock(spec=discord.Role, position=5, id=1)

    for builder in (
        build_moderation_staff_overwrites,
        build_commands_channel_overwrites,
    ):
        overwrites = dict(builder(guild, bot, human_mod))
        assert everyone in overwrites
        assert overwrites[everyone].view_channel is False
        assert access not in overwrites
        assert human_mod in overwrites
        assert overwrites[human_mod].view_channel is True


def test_commands_channel_allows_slash_commands_for_moderators_only() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.default_role = MagicMock(spec=discord.Role)
    human_mod = MagicMock(spec=discord.Role, position=3, id=99)
    bot = MagicMock(spec=discord.Member)
    bot.top_role = MagicMock(spec=discord.Role, position=5, id=1)

    overwrites = dict(build_commands_channel_overwrites(guild, bot, human_mod))
    assert overwrites[guild.default_role].use_application_commands is not True
    assert overwrites[human_mod].use_application_commands is True


def test_subscribe_announcement_channel_allows_everyone_readonly() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    guild.default_role = everyone
    access = MagicMock(spec=discord.Role, position=2)
    human_mod = MagicMock(spec=discord.Role, position=3, id=99)
    bot = MagicMock(spec=discord.Member)
    bot.top_role = MagicMock(spec=discord.Role, position=5, id=1)

    overwrites = dict(
        build_subscribe_announcement_channel_overwrites(guild, bot, access, human_mod)
    )
    assert overwrites[everyone].view_channel is True
    assert overwrites[everyone].send_messages is False
    assert overwrites[everyone].read_message_history is True
