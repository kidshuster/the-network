from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import discord

from bot.services.guild_permissions import (
    build_commands_channel_overwrites,
    build_moderation_staff_overwrites,
    build_subscribe_announcement_channel_overwrites,
)


def test_moderation_channels_deny_everyone() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    guild.default_role = everyone
    human_mod = MagicMock(spec=discord.Role, position=3, id=99)
    bot = MagicMock(spec=discord.Member, id=999)
    bot.top_role = MagicMock(spec=discord.Role, position=5, id=1)

    for builder in (
        build_moderation_staff_overwrites,
        build_commands_channel_overwrites,
    ):
        overwrites = dict(builder(guild, bot, human_mod))
        assert everyone in overwrites
        assert overwrites[everyone].view_channel is False
        assert human_mod in overwrites
        assert overwrites[human_mod].view_channel is True
        assert bot not in overwrites


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
    access = MagicMock(spec=discord.Role, position=2, id=88)
    access.is_default.return_value = False
    human_mod = MagicMock(spec=discord.Role, position=3, id=99)
    human_mod.is_default.return_value = False
    bot = MagicMock(spec=discord.Member, id=999)
    bot.top_role = MagicMock(spec=discord.Role, position=5, id=1)

    overwrites = dict(
        build_subscribe_announcement_channel_overwrites(
            guild, bot, access, human_mod
        )
    )
    assert overwrites[everyone].view_channel is True
    assert overwrites[everyone].send_messages is False
    assert overwrites[everyone].create_public_threads is None
    assert overwrites[everyone].add_reactions is None
    assert overwrites[everyone].read_message_history is True
    assert overwrites[access].view_channel is True
    assert overwrites[human_mod].create_public_threads is None


def test_everyone_hidden_overwrite_denies_threads() -> None:
    from bot.services.guild_permissions import build_everyone_hidden_overwrite

    hidden = build_everyone_hidden_overwrite()
    assert hidden.view_channel is False
    assert hidden.send_messages is False
    assert hidden.create_public_threads is False


def test_filter_configurable_overwrites_skips_high_roles() -> None:
    from bot.services.guild_permissions import filter_configurable_overwrites

    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone
    high_role = MagicMock(spec=discord.Role, position=10, id=50)
    high_role.is_default.return_value = False
    low_role = MagicMock(spec=discord.Role, position=1, id=51)
    low_role.is_default.return_value = False
    bot = MagicMock(spec=discord.Member, id=999)
    bot.top_role = MagicMock(spec=discord.Role, position=5, id=1)
    bot.roles = [bot.top_role]
    perms = MagicMock(administrator=False)
    type(bot).guild_permissions = PropertyMock(return_value=perms)

    source = {
        everyone: discord.PermissionOverwrite(view_channel=True),
        high_role: discord.PermissionOverwrite(view_channel=True),
        low_role: discord.PermissionOverwrite(manage_webhooks=True),
        bot: discord.PermissionOverwrite(view_channel=True),
    }
    filtered = filter_configurable_overwrites(bot, source)

    assert everyone in filtered
    assert high_role not in filtered
    assert low_role in filtered
    assert bot in filtered

    channel_filtered = filter_configurable_overwrites(bot, source, for_channel=True)
    assert bot not in channel_filtered


def test_partner_feed_overwrite_allows_webhooks_only() -> None:
    from bot.services.guild_permissions import build_partner_feed_overwrite

    partner = build_partner_feed_overwrite()
    assert partner.view_channel is True
    assert partner.manage_webhooks is True
    assert partner.send_messages is False
    assert partner.create_public_threads is False


def test_prepare_category_create_overwrites_omits_bot_and_operator() -> None:
    from bot.services.guild_permissions import prepare_category_create_overwrites

    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    client = MagicMock(spec=discord.Role, id=10)
    operator = MagicMock(spec=discord.Role, id=50)
    bot = MagicMock(spec=discord.Member, id=999)
    bot.top_role = operator
    overwrite = discord.PermissionOverwrite(view_channel=True)

    prepared = prepare_category_create_overwrites(
        bot,
        {
            everyone: overwrite,
            client: overwrite,
            bot: overwrite,
            operator: overwrite,
        },
    )

    assert everyone in prepared
    assert client in prepared
    assert bot not in prepared
    assert operator not in prepared
