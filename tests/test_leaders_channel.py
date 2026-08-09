from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.services.guild_permissions import (
    build_changelog_channel_overwrites,
    build_leaders_category_overwrites,
    build_leaders_channel_overwrites,
)


def test_leaders_channel_overwrites_hide_everyone_and_grant_client_roles() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    client_a = MagicMock(spec=discord.Role)
    client_a.id = 101
    client_a.position = 1
    client_b = MagicMock(spec=discord.Role)
    client_b.id = 102
    client_b.position = 2

    access = MagicMock(spec=discord.Role)
    access.id = 201
    access.position = 3

    overwrites = dict(
        build_leaders_channel_overwrites(
            guild,
            bot_member,
            [client_a, client_b],
            access,
            None,
        )
    )

    assert overwrites[everyone].view_channel is False
    assert overwrites[client_a].view_channel is True
    assert overwrites[client_a].read_message_history is True
    assert overwrites[client_a].send_messages is True
    assert overwrites[client_b].read_message_history is True
    assert overwrites[client_b].send_messages is True
    assert overwrites[access].view_channel is False


def test_leaders_channel_overwrites_grant_moderator_role() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    client = MagicMock(spec=discord.Role)
    client.id = 101
    client.position = 1

    access = MagicMock(spec=discord.Role)
    access.id = 201
    access.position = 3

    moderator = MagicMock(spec=discord.Role)
    moderator.id = 301
    moderator.position = 5

    overwrites = dict(
        build_leaders_channel_overwrites(
            guild,
            bot_member,
            [client],
            access,
            moderator,
        )
    )

    assert overwrites[everyone].view_channel is False
    assert overwrites[access].view_channel is False
    assert overwrites[client].view_channel is True
    assert overwrites[moderator].view_channel is True
    assert len(overwrites) == 4


def test_leaders_category_overwrites_hide_everyone_and_access_role() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    client = MagicMock(spec=discord.Role)
    client.id = 101
    client.position = 1

    access = MagicMock(spec=discord.Role)
    access.id = 201
    access.position = 3

    overwrites = dict(
        build_leaders_category_overwrites(
            guild,
            bot_member,
            [client],
            access,
            None,
        )
    )

    assert overwrites[everyone].view_channel is False
    assert overwrites[access].view_channel is False
    assert overwrites[client].view_channel is True
    assert overwrites[client].read_message_history is True
    assert overwrites[client].send_messages is True
    assert overwrites[client].embed_links is True
    assert overwrites[client].attach_files is True
    assert overwrites[client].add_reactions is True


def test_leaders_channel_overwrites_include_operator_role() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    client = MagicMock(spec=discord.Role)
    client.id = 101
    client.position = 1

    access = MagicMock(spec=discord.Role)
    access.id = 201
    access.position = 3

    operator = MagicMock(spec=discord.Role)
    operator.id = 301
    operator.position = 9

    overwrites = dict(
        build_leaders_channel_overwrites(
            guild,
            bot_member,
            [client],
            access,
            None,
            operator_role=operator,
        )
    )

    assert overwrites[operator].view_channel is True
    assert overwrites[operator].manage_channels is True


def test_leaders_channel_overwrites_include_operator_when_it_is_top_role() -> None:
    """Operator is usually the bot's top role — must still appear on channel overwrites."""
    from bot.services.guild_permissions import filter_configurable_overwrites

    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    operator = MagicMock(spec=discord.Role)
    operator.id = 301
    operator.position = 10
    operator.is_default.return_value = False

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = operator

    client = MagicMock(spec=discord.Role)
    client.id = 101
    client.position = 1
    client.is_default.return_value = False

    access = MagicMock(spec=discord.Role)
    access.id = 201
    access.position = 3
    access.is_default.return_value = False

    overwrites = dict(
        build_leaders_channel_overwrites(
            guild,
            bot_member,
            [client],
            access,
            None,
            operator_role=operator,
        )
    )
    safe = filter_configurable_overwrites(bot_member, overwrites, for_channel=True)

    assert operator in safe
    assert safe[operator].manage_channels is True


def test_leaders_category_overwrites_include_operator_role() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    client = MagicMock(spec=discord.Role)
    client.id = 101
    client.position = 1

    access = MagicMock(spec=discord.Role)
    access.id = 201
    access.position = 3

    operator = MagicMock(spec=discord.Role)
    operator.id = 301
    operator.position = 9

    overwrites = dict(
        build_leaders_category_overwrites(
            guild,
            bot_member,
            [client],
            access,
            None,
            operator_role=operator,
        )
    )

    assert overwrites[operator].view_channel is True
    assert overwrites[operator].manage_channels is True


def test_changelog_channel_overwrites_are_readonly_for_client_roles() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    client = MagicMock(spec=discord.Role)
    client.id = 101
    client.position = 1

    access = MagicMock(spec=discord.Role)
    access.id = 201
    access.position = 3

    moderator = MagicMock(spec=discord.Role)
    moderator.id = 301
    moderator.position = 5

    overwrites = dict(
        build_changelog_channel_overwrites(
            guild,
            bot_member,
            [client],
            access,
            moderator,
        )
    )

    assert overwrites[everyone].view_channel is False
    assert overwrites[access].view_channel is False
    assert overwrites[client].view_channel is True
    assert overwrites[client].read_message_history is True
    assert overwrites[client].send_messages is False
    assert overwrites[client].embed_links is False
    assert overwrites[client].attach_files is False
    assert overwrites[client].add_reactions is False
    assert overwrites[moderator].view_channel is True
    assert overwrites[moderator].send_messages is True
