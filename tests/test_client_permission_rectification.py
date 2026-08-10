from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.domain.client import Client
from bot.services.client_permission_rectification import rectify_client_permissions
from bot.services.guild_init import GuildInitResult
from bot.services.guild_layout import resolve_leaders_channel


def test_resolve_leaders_channel_finds_legacy_name_in_leaders_category() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.text_channels = []

    leaders_category = MagicMock(spec=discord.CategoryChannel)
    leaders_category.id = 100
    leaders_category.name = "Leaders"

    legacy = MagicMock(spec=discord.TextChannel)
    legacy.id = 200
    legacy.name = "leaders"
    legacy.category_id = 100

    guild.categories = [leaders_category]
    guild.text_channels = [legacy]

    assert resolve_leaders_channel(guild) is legacy


async def test_rectify_client_permissions_syncs_category_and_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.edit = AsyncMock()

    client_role = MagicMock(spec=discord.Role)
    client_role.id = 20
    client_role.position = 1
    client_role.is_default.return_value = False

    profile = MagicMock(spec=discord.TextChannel)
    profile.id = 30
    profile.mention = "#acme-profile"
    profile.permissions_synced = False
    profile.edit = AsyncMock()
    profile.set_permissions = AsyncMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    access_role = MagicMock(spec=discord.Role)
    access_role.id = 40
    access_role.position = 5
    access_role.is_default.return_value = False

    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {10: category, 30: profile}.get(channel_id),
    )
    guild.get_role = MagicMock(return_value=client_role)

    client = Client(
        id=1,
        guild_id=1,
        server_name="Acme",
        display_name="Acme",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
        timecode_enabled=False,
    )

    context = MagicMock()
    context.client_repo.list_subscriptions_by_client = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "bot.services.client_subscription.resolve_access_role",
        MagicMock(return_value=access_role),
    )
    monkeypatch.setattr(
        "bot.services.client_subscription.resolve_human_moderator_role",
        MagicMock(return_value=None),
    )

    result = await rectify_client_permissions(
        guild,
        bot_member,
        context,
        client,
        access_role=access_role,
        human_moderator_role=None,
        access_role_name="The Network",
    )

    assert "category" in result.synced
    assert any("#acme-profile" in item for item in result.synced)
    category.edit.assert_awaited_once()
    profile.edit.assert_awaited()
    assert profile.edit.await_args.kwargs.get("sync_permissions") is False


async def test_rectify_client_permissions_skips_when_category_missing() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.get_channel = MagicMock(return_value=None)
    guild.get_role = MagicMock(return_value=MagicMock(spec=discord.Role))
    bot = MagicMock(spec=discord.Member)
    context = MagicMock()
    client = Client(
        id=1,
        guild_id=1,
        server_name="Acme",
        display_name="Acme",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        timecode_enabled=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )

    result = await rectify_client_permissions(
        guild,
        bot,
        context,
        client,
        access_role=MagicMock(spec=discord.Role),
        human_moderator_role=None,
        access_role_name="The Network",
    )

    assert result.skipped == ["category missing in Discord"]
    assert not result.synced


async def test_rectify_client_permissions_records_category_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from discord_helpers import http_50013

    guild = MagicMock(spec=discord.Guild)
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    client_role = MagicMock(spec=discord.Role, id=20)
    guild.get_channel = MagicMock(return_value=category)
    guild.get_role = MagicMock(return_value=client_role)

    monkeypatch.setattr(
        "bot.services.client_permission_rectification.sync_client_category_permissions",
        AsyncMock(side_effect=http_50013()),
    )
    monkeypatch.setattr(
        "bot.services.client_permission_rectification.sync_client_profile_channel_permissions",
        AsyncMock(),
    )

    context = MagicMock()
    context.client_repo.list_subscriptions_by_client = AsyncMock(return_value=[])

    client = Client(
        id=1,
        guild_id=1,
        server_name="Acme",
        display_name="Acme",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        timecode_enabled=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )

    result = await rectify_client_permissions(
        guild,
        MagicMock(spec=discord.Member),
        context,
        client,
        access_role=MagicMock(spec=discord.Role),
        human_moderator_role=None,
        access_role_name="The Network",
    )

    assert result.failures
    assert "category" in result.failures[0].casefold()
    assert not any("category" == item for item in result.synced)


async def test_rectify_client_permissions_syncs_subscription_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    client_role = MagicMock(spec=discord.Role, id=20)
    profile = MagicMock(spec=discord.TextChannel, id=30, mention="#acme-profile")
    publish = MagicMock(spec=discord.TextChannel, id=40, mention="#acme-stingers-publish")
    subscribe = MagicMock(spec=discord.TextChannel, id=41, mention="#acme-stingers-subscribe")

    guild.get_channel = MagicMock(
        side_effect=lambda cid: {
            10: category,
            30: profile,
            40: publish,
            41: subscribe,
        }.get(cid),
    )
    guild.get_role = MagicMock(return_value=client_role)

    sync_sub = AsyncMock()
    monkeypatch.setattr(
        "bot.services.client_permission_rectification.sync_client_category_permissions",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.services.client_permission_rectification.sync_client_profile_channel_permissions",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.services.client_permission_rectification.sync_subscription_channel_permissions",
        sync_sub,
    )

    from subscription_helpers import make_client_subscription

    from bot.domain.network import Network

    subscription = make_client_subscription(
        id=1,
        publish_channel_id=40,
        subscribe_channel_id=41,
    )
    network = Network(
        id=2,
        key="stingers",
        display_name="Stingers",
        feed_category_id=None,
        output_channel_id=None,
        concat_channel_id=None,
        profile_forum_channel_id=None,
        join_channel_id=None,
        enabled=True,
    )

    context = MagicMock()
    context.client_repo.list_subscriptions_by_client = AsyncMock(return_value=[subscription])
    context.network_repo.get_by_id = AsyncMock(return_value=network)

    client = Client(
        id=1,
        guild_id=1,
        server_name="Acme",
        display_name="Acme",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        timecode_enabled=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )

    result = await rectify_client_permissions(
        guild,
        MagicMock(spec=discord.Member),
        context,
        client,
        access_role=MagicMock(spec=discord.Role),
        human_moderator_role=None,
        access_role_name="The Network",
    )

    sync_sub.assert_awaited_once()
    assert any("stingers" in item for item in result.synced)


def test_guild_init_result_tracks_rectification_fields() -> None:
    result = GuildInitResult(success=True)
    result.rectifications.append("Leaders access synced.")
    result.rectification_skipped.append("**Acme**: client role missing in Discord")
    result.rectification_failures.append("Leaders: could not sync #leaders-channel.")

    assert len(result.rectifications) == 1
    assert len(result.rectification_skipped) == 1
    assert len(result.rectification_failures) == 1
