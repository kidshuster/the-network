from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import discord

from bot.layout import preset_overwrite
from bot.permissions.service import (
    ResourceKind,
    applicable_overwrites,
    build_context,
)


def test_everyone_hidden_overwrite_denies_threads() -> None:
    hidden = preset_overwrite("everyone_hidden")
    assert hidden.view_channel is False
    assert hidden.send_messages is False
    assert hidden.create_public_threads is False


def test_partner_feed_overwrite_allows_webhooks_only() -> None:
    partner = preset_overwrite("partner_feed")
    assert partner.view_channel is True
    assert partner.manage_webhooks is True
    assert partner.send_messages is False
    assert partner.create_public_threads is False


def test_applicable_overwrites_skips_high_roles() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone
    high_role = MagicMock(spec=discord.Role, position=10, id=50)
    high_role.is_default.return_value = False
    low_role = MagicMock(spec=discord.Role, position=1, id=51)
    low_role.is_default.return_value = False
    bot = MagicMock(spec=discord.Member, id=999)
    bot.guild = guild
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
    context = build_context(guild, bot, access_role=None, moderator_role=None)
    filtered = applicable_overwrites(context, source, kind=ResourceKind.CATEGORY)

    assert everyone in filtered
    assert high_role not in filtered
    assert low_role in filtered
    assert bot in filtered

    channel_filtered = applicable_overwrites(context, source, kind=ResourceKind.TEXT)
    assert bot not in channel_filtered


def test_category_create_applicable_overwrites_omits_bot_and_operator() -> None:
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    client = MagicMock(spec=discord.Role, id=10)
    operator = MagicMock(spec=discord.Role, id=50)
    bot = MagicMock(spec=discord.Member, id=999)
    bot.guild = MagicMock(spec=discord.Guild)
    bot.top_role = operator
    overwrite = discord.PermissionOverwrite(view_channel=True)

    prepared = applicable_overwrites(
        build_context(bot.guild, bot, access_role=None, moderator_role=None),
        {
            everyone: overwrite,
            client: overwrite,
            bot: overwrite,
            operator: overwrite,
        },
        kind=ResourceKind.CATEGORY,
        for_category_create=True,
    )

    assert everyone in prepared
    assert client in prepared
    assert bot not in prepared
    assert operator not in prepared
