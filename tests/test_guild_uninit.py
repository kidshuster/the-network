from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from bot.constants import (
    DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    LEGACY_MODERATOR_ROLE_NAME,
)
from bot.hub.resolve import CHANNEL_MODERATOR_ONLY, CHANNEL_RULES
from bot.hub.uninit import (
    collect_uninit_targets,
    is_deletable_hub_role,
    is_hub_managed_category,
    is_preserved_hub_channel,
    uninitialize_guild,
)


def test_is_preserved_hub_channel_rules_and_moderator_only() -> None:
    guild = MagicMock(spec=discord.Guild)
    rules = MagicMock(spec=discord.TextChannel, id=10)
    rules.name = CHANNEL_RULES
    guild.rules_channel = rules
    mod = MagicMock(spec=discord.TextChannel, id=11)
    mod.name = CHANNEL_MODERATOR_ONLY
    other = MagicMock(spec=discord.TextChannel, id=12)
    other.name = "commands"

    assert is_preserved_hub_channel(guild, rules) is True
    assert is_preserved_hub_channel(guild, mod) is True
    assert is_preserved_hub_channel(guild, other) is False


def test_is_hub_managed_category() -> None:
    hub = MagicMock(spec=discord.CategoryChannel)
    hub.name = "Subscribe To Me!"
    feed = MagicMock(spec=discord.CategoryChannel)
    feed.name = "Stingers Feed"
    other = MagicMock(spec=discord.CategoryChannel)
    other.name = "General"

    assert is_hub_managed_category(hub) is True
    assert is_hub_managed_category(feed) is True
    assert is_hub_managed_category(other) is False


def test_is_deletable_hub_role() -> None:
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    everyone.managed = False

    bot_role = MagicMock(spec=discord.Role, managed=True)
    bot_role.is_default.return_value = False
    bot_role.name = "The Network"

    moderator = MagicMock(spec=discord.Role, managed=False)
    moderator.is_default.return_value = False
    moderator.name = LEGACY_MODERATOR_ROLE_NAME

    partner = MagicMock(spec=discord.Role, managed=False)
    partner.is_default.return_value = False
    partner.name = "Partner: Acme"

    client_role = MagicMock(spec=discord.Role, managed=False)
    client_role.is_default.return_value = False
    client_role.name = "Client: Acme"

    custom = MagicMock(spec=discord.Role, managed=False)
    custom.is_default.return_value = False
    custom.name = "VIP"

    operator = MagicMock(spec=discord.Role, managed=False)
    operator.is_default.return_value = False
    operator.name = "The Network+"

    assert is_deletable_hub_role(
        everyone,
        access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
        operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    ) is False
    assert is_deletable_hub_role(
        bot_role,
        access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
        operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    ) is False
    assert is_deletable_hub_role(
        operator,
        access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
        operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    ) is False
    assert is_deletable_hub_role(
        moderator,
        access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
        operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    ) is True
    assert is_deletable_hub_role(
        partner,
        access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
        operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    ) is False
    assert is_deletable_hub_role(
        client_role,
        access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
        operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    ) is False
    assert is_deletable_hub_role(
        custom,
        access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
        operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    ) is False


def test_collect_uninit_targets_preserves_rules_and_moderator_only() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.rules_channel = None
    guild.roles = []

    subscribe = MagicMock(spec=discord.CategoryChannel, id=100, name="Subscribe To Me!")
    feed = MagicMock(spec=discord.CategoryChannel, id=200, name="Stingers Feed")
    guild.categories = [subscribe, feed]

    rules = MagicMock(spec=discord.TextChannel, id=1, category_id=100)
    rules.name = CHANNEL_RULES
    mod = MagicMock(spec=discord.TextChannel, id=2, category_id=100)
    mod.name = CHANNEL_MODERATOR_ONLY
    announce = MagicMock(
        spec=discord.TextChannel, id=3, name="stingers-announcements", category_id=100
    )
    announce.type = discord.ChannelType.news
    join = MagicMock(spec=discord.TextChannel, id=4, name="join-stingers", category_id=100)
    join.type = discord.ChannelType.text
    sink = MagicMock(spec=discord.TextChannel, id=5, name="welcome-sink", category_id=None)
    sink.type = discord.ChannelType.text

    guild.channels = [subscribe, feed, rules, mod, announce, join, sink]

    channels, categories, roles, preserved = collect_uninit_targets(guild)

    assert {ch.id for ch in preserved} == {1, 2}
    assert {ch.id for ch in channels} == {3, 4, 5}
    assert {cat.id for cat in categories} == {100, 200}
    assert roles == []


def test_collect_uninit_targets_preserves_rules_channel_by_id() -> None:
    guild = MagicMock(spec=discord.Guild)
    rules = MagicMock(spec=discord.TextChannel, id=99, category_id=100)
    rules.name = "community-rules"
    guild.rules_channel = rules
    guild.roles = []

    subscribe = MagicMock(spec=discord.CategoryChannel, id=100, name="Subscribe To Me!")
    guild.categories = [subscribe]
    guild.channels = [subscribe, rules]

    channels, categories, roles, preserved = collect_uninit_targets(guild)

    assert {ch.id for ch in preserved} == {99}
    assert channels == []
    assert {cat.id for cat in categories} == {100}
    assert roles == []


def test_collect_uninit_targets_includes_legacy_moderator_role() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.rules_channel = None
    guild.categories = []
    guild.channels = []

    moderator = MagicMock(spec=discord.Role, managed=False)
    moderator.is_default.return_value = False
    moderator.name = LEGACY_MODERATOR_ROLE_NAME
    guild.roles = [moderator]

    _, _, roles, _ = collect_uninit_targets(guild)

    assert roles == [moderator]


@pytest.mark.asyncio
async def test_uninitialize_guild_fails_without_manage_channels() -> None:
    guild = MagicMock(spec=discord.Guild)
    bot_member = MagicMock(spec=discord.Member)
    perms = MagicMock()
    perms.manage_channels = False
    bot_member.guild_permissions = perms

    result = await uninitialize_guild(guild, bot_member)

    assert result.success is False
    assert result.reason is not None
    assert "Manage Channels" in result.reason


@pytest.mark.asyncio
async def test_uninitialize_guild_deletes_hub_targets_and_preserves_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    guild = MagicMock(spec=discord.Guild)
    rules = MagicMock(spec=discord.TextChannel, id=99, category_id=100)
    rules.name = CHANNEL_RULES
    guild.rules_channel = rules

    hub_channel = MagicMock(spec=discord.TextChannel, id=200, category_id=100)
    hub_channel.name = "join-the-network"
    subscribe = MagicMock(spec=discord.CategoryChannel, id=100)
    subscribe.name = "Subscribe To Me!"
    guild.categories = [subscribe]
    guild.channels = [subscribe, rules, hub_channel]

    partner = MagicMock(spec=discord.Role, managed=False, position=1)
    partner.is_default.return_value = False
    partner.name = LEGACY_MODERATOR_ROLE_NAME
    guild.roles = [partner]

    bot_member = MagicMock(spec=discord.Member)
    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = True
    bot_member.guild_permissions = perms

    delete_channel = AsyncMock(return_value=True)
    delete_role = AsyncMock(return_value=True)
    monkeypatch.setattr("bot.hub.uninit.delete_channel", delete_channel)
    monkeypatch.setattr("bot.hub.uninit.delete_role", delete_role)
    rules.edit = AsyncMock()

    result = await uninitialize_guild(guild, bot_member)

    assert result.success is True
    assert result.preserved_channels == ["#rules"]
    assert result.deleted_channels == ["#join-the-network"]
    assert result.deleted_categories == ["Subscribe To Me!"]
    assert result.deleted_roles == [LEGACY_MODERATOR_ROLE_NAME]
    rules.edit.assert_awaited_once()
