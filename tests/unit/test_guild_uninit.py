from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from bot.constants import (
    DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    LEGACY_MODERATOR_ROLE_NAME,
)
from bot.features.channels.resolve import CHANNEL_ADMIN, CHANNEL_RULES
from bot.features.recipes.hub.uninitialize import (
    collect_uninit_targets,
    is_deletable_hub_role,
    is_hub_managed_category,
    is_preserved_hub_channel,
    uninitialize_guild,
)


def test_is_preserved_hub_channel_rules_and_admin() -> None:
    guild = MagicMock(spec=discord.Guild)
    rules = MagicMock(spec=discord.TextChannel, id=10)
    rules.name = CHANNEL_RULES
    guild.rules_channel = rules
    mod = MagicMock(spec=discord.TextChannel, id=11)
    mod.name = CHANNEL_ADMIN
    other = MagicMock(spec=discord.TextChannel, id=12)
    other.name = "commands"

    assert is_preserved_hub_channel(guild, rules) is True
    assert is_preserved_hub_channel(guild, mod) is True
    assert is_preserved_hub_channel(guild, other) is False


def test_is_hub_managed_category() -> None:
    hub = MagicMock(spec=discord.CategoryChannel)
    hub.name = "Moderation"
    feed = MagicMock(spec=discord.CategoryChannel)
    feed.name = "Stingers Feed"
    other = MagicMock(spec=discord.CategoryChannel)
    other.name = "General"

    assert is_hub_managed_category(hub) is True
    assert is_hub_managed_category(feed) is False
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

    assert (
        is_deletable_hub_role(
            everyone,
            access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
            operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
        )
        is False
    )
    assert (
        is_deletable_hub_role(
            bot_role,
            access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
            operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
        )
        is False
    )
    assert (
        is_deletable_hub_role(
            operator,
            access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
            operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
        )
        is False
    )
    assert (
        is_deletable_hub_role(
            moderator,
            access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
            operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
        )
        is True
    )
    assert (
        is_deletable_hub_role(
            partner,
            access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
            operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
        )
        is False
    )
    assert (
        is_deletable_hub_role(
            client_role,
            access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
            operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
        )
        is False
    )
    assert (
        is_deletable_hub_role(
            custom,
            access_role_name=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
            operator_role_name=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
        )
        is False
    )


def test_collect_uninit_targets_preserves_rules_and_admin() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.rules_channel = None
    guild.roles = []

    moderation = MagicMock(spec=discord.CategoryChannel, id=100, name="Moderation")
    network = MagicMock(spec=discord.CategoryChannel, id=200, name="The Network")
    moderation.name = "Moderation"
    network.name = "The Network"
    guild.categories = [moderation, network]

    rules = MagicMock(spec=discord.TextChannel, id=1, category_id=100)
    rules.name = CHANNEL_RULES
    mod = MagicMock(spec=discord.TextChannel, id=2, category_id=100)
    mod.name = CHANNEL_ADMIN
    announce = MagicMock(
        spec=discord.TextChannel, id=3, name="stingers-announcements", category_id=100
    )
    announce.type = discord.ChannelType.news
    join = MagicMock(spec=discord.TextChannel, id=4, name="join-stingers", category_id=100)
    join.type = discord.ChannelType.text
    guild.channels = [moderation, network, rules, mod, announce, join]

    channels, categories, roles, preserved = collect_uninit_targets(guild)

    assert {ch.id for ch in preserved} == {1, 2}
    assert {ch.id for ch in channels} == {3, 4}
    assert {cat.id for cat in categories} == {100, 200}
    assert roles == []


def test_collect_uninit_targets_preserves_rules_channel_by_id() -> None:
    guild = MagicMock(spec=discord.Guild)
    rules = MagicMock(spec=discord.TextChannel, id=99, category_id=100)
    rules.name = "community-rules"
    guild.rules_channel = rules
    guild.roles = []

    network = MagicMock(spec=discord.CategoryChannel, id=100, name="The Network")
    network.name = "The Network"
    guild.categories = [network]
    guild.channels = [network, rules]

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

    from bot.features.channels.layout.applier import BatchApplyResult, ResourceApplyResult

    guild = MagicMock(spec=discord.Guild)
    rules = MagicMock(spec=discord.TextChannel, id=99, category_id=100)
    rules.name = CHANNEL_RULES
    guild.rules_channel = rules
    guild.public_updates_channel = None
    guild.text_channels = []
    guild.categories = []
    guild.channels = []

    partner = MagicMock(spec=discord.Role, managed=False, position=1)
    partner.is_default.return_value = False
    partner.name = LEGACY_MODERATOR_ROLE_NAME
    guild.roles = [partner]

    bot_member = MagicMock(spec=discord.Member)
    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = True
    bot_member.guild_permissions = perms

    batch = BatchApplyResult(
        results=[
            ResourceApplyResult(
                resource_id="detach:rules",
                success=True,
                changed=True,
                channel=rules,
            ),
            ResourceApplyResult(
                resource_id="delete:join-the-network",
                success=True,
                changed=True,
            ),
            ResourceApplyResult(
                resource_id="delete_cat:The Network",
                success=True,
                changed=True,
            ),
        ]
    )
    apply_layout = AsyncMock(return_value=batch)
    delete_role = AsyncMock(return_value=True)
    monkeypatch.setattr("bot.features.recipes.hub.uninitialize.apply_layout", apply_layout)
    monkeypatch.setattr("bot.features.recipes.hub.uninitialize.delete_role", delete_role)
    monkeypatch.setattr(
        "bot.features.recipes.hub.uninitialize.resolve_access_role_by_name",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.uninitialize.resolve_operator_role_by_name",
        MagicMock(return_value=None),
    )

    result = await uninitialize_guild(guild, bot_member)

    assert result.success is True
    assert result.preserved_channels == ["#rules"]
    assert result.deleted_channels == ["#join-the-network"]
    assert result.deleted_categories == ["The Network"]
    assert result.deleted_roles == [LEGACY_MODERATOR_ROLE_NAME]
    apply_layout.assert_awaited_once()
