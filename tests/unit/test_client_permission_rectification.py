from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.app.layout.applier import BatchApplyResult, ResourceApplyResult
from bot.core.models.client import Client
from bot.features.recipes.hub.clients.rectification import rectify_client_permissions


async def test_rectify_client_permissions_syncs_category_and_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.name = "Acme"
    client_role = MagicMock(spec=discord.Role)
    client_role.id = 20
    profile = MagicMock(spec=discord.TextChannel)
    profile.id = 30
    profile.mention = "#acme-profile"

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
    context.store.clients.list_subscriptions_by_client = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.rectification.resolve_operator_role_by_name",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.rectification.apply_layout",
        AsyncMock(
            return_value=BatchApplyResult(
                results=[
                    ResourceApplyResult("client", True, channel=category),
                    ResourceApplyResult("profile", True, channel=profile),
                ]
            )
        ),
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

    assert "category" in result.synced
    assert any("#acme-profile" in item for item in result.synced)


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
    guild = MagicMock(spec=discord.Guild)
    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.name = "Acme"
    client_role = MagicMock(spec=discord.Role, id=20)
    guild.get_channel = MagicMock(return_value=category)
    guild.get_role = MagicMock(return_value=client_role)

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.rectification.resolve_operator_role_by_name",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.rectification.apply_layout",
        AsyncMock(
            return_value=BatchApplyResult(
                results=[
                    ResourceApplyResult(
                        "client",
                        False,
                        detail="Missing Permissions",
                    )
                ]
            )
        ),
    )

    context = MagicMock()
    context.store.clients.list_subscriptions_by_client = AsyncMock(return_value=[])

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
    assert not any(item == "category" for item in result.synced)


async def test_rectify_client_permissions_syncs_subscription_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.name = "Acme"
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

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.rectification.resolve_operator_role_by_name",
        MagicMock(return_value=None),
    )

    async def _apply(
        _ctx: object,
        resources: list[object],
        *,
        mode: object = None,
    ) -> BatchApplyResult:
        ids = [getattr(r, "id", None) for r in resources]
        assert ids == ["client", "profile", "publish", "subscribe"]
        return BatchApplyResult(
            results=[
                ResourceApplyResult("client", True, channel=category),
                ResourceApplyResult("profile", True, channel=profile),
                ResourceApplyResult("publish", True, channel=publish),
                ResourceApplyResult("subscribe", True, channel=subscribe),
            ]
        )

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.rectification.apply_layout",
        AsyncMock(side_effect=_apply),
    )

    from subscription_helpers import make_client_subscription

    from bot.core.models.network import Network

    subscription = make_client_subscription(
        id=1,
        client_id=1,
        network_id=2,
        network_key="stingers",
        publish_channel_id=40,
        subscribe_channel_id=41,
    )
    context = MagicMock()
    context.store.clients.list_subscriptions_by_client = AsyncMock(return_value=[subscription])
    context.store.networks.get_by_id = AsyncMock(
        return_value=Network(
            id=2,
            key="stingers",
            display_name="Stingers",
            feed_category_id=None,
            output_channel_id=None,
            concat_channel_id=None,
            profile_forum_channel_id=None,
            enabled=True,
            join_channel_id=None,
        )
    )

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

    assert any("publish" in item for item in result.synced)
    assert any("subscribe" in item for item in result.synced)
