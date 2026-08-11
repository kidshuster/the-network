from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from widget_helpers import wire_widget_bot

from bot.app.context import BotContext
from bot.app.widgets import render_view
from bot.core.clients.cache import ClientCache
from bot.core.database.store import Store
from bot.core.networks.routing import RoutingService
from bot.features.recipes.hub.clients.deletion import delete_client_resources


def _make_context(db) -> BotContext:
    store = Store.create(db)
    routing = RoutingService(store.networks, store.clients)
    client_cache = ClientCache(store.clients)
    routing.attach_client_cache(client_cache)
    return BotContext.create(
        settings=MagicMock(),
        db=db,
        store=store,
        routing_service=routing,
        client_cache=client_cache,
        relay_service=MagicMock(),
        bot_settings=MagicMock(),
    )


def test_network_profile_view_has_edit_and_delete_buttons() -> None:
    bot = wire_widget_bot()
    view = render_view("network_profile", bot, client_id=1, network_keys=["stingers"])
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert "Edit Profile" in labels
    assert "Delete Client" in labels


def test_network_profile_view_stays_within_discord_component_limit() -> None:
    bot = wire_widget_bot()
    network_keys = [f"net{i}" for i in range(30)]
    view = render_view(
        "network_profile",
        bot,
        client_id=1,
        network_keys=network_keys,
        timecode_enabled=True,
    )
    assert len(view.children) <= 25


@pytest.mark.asyncio
async def test_delete_client_removes_subscriptions_blacklists_and_client(db) -> None:
    context = _make_context(db)
    network = await context.store.networks.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    client = await context.store.clients.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    other_client = await context.store.clients.create(
        guild_id=100,
        server_name="beta",
        display_name="Beta",
        category_id=20,
        client_role_id=21,
        profile_channel_id=31,
        profile_message_id=41,
    )
    subscription = await context.store.clients.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=203,
        subscribe_channel_id=202,
    )
    other_subscription = await context.store.clients.create_subscription(
        client_id=other_client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=303,
        subscribe_channel_id=302,
    )
    await context.store.clients.add_blacklist(subscription.id, other_client.id)
    await context.store.clients.add_blacklist(other_subscription.id, client.id)

    profile = MagicMock(spec=discord.TextChannel)
    profile.id = 30
    profile.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
    publish = MagicMock(spec=discord.TextChannel)
    publish.id = 203
    publish.webhooks = AsyncMock(return_value=[])
    subscribe = MagicMock(spec=discord.TextChannel)
    subscribe.id = 202
    category_channels = [profile, subscribe, publish]

    async def _remove_channel(channel: MagicMock) -> None:
        if channel in category_channels:
            category_channels.remove(channel)

    def _make_delete(channel: MagicMock) -> AsyncMock:
        async def _delete(**_: object) -> None:
            await _remove_channel(channel)

        return AsyncMock(side_effect=_delete)

    profile.delete = _make_delete(profile)
    publish.delete = _make_delete(publish)
    subscribe.delete = _make_delete(subscribe)

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.channels = category_channels
    category.delete = AsyncMock()

    client_role = MagicMock(spec=discord.Role)
    client_role.id = 11
    client_role.delete = AsyncMock()

    member = MagicMock(spec=discord.Member)
    member.roles = []
    member.remove_roles = AsyncMock()

    guild = MagicMock(spec=discord.Guild)
    guild.me = MagicMock(spec=discord.Member)
    guild.members = [member]
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {
            30: profile,
            202: subscribe,
            203: publish,
            10: category,
        }.get(channel_id)
    )
    guild.get_role = MagicMock(return_value=client_role)

    context.refresh_projections = AsyncMock()

    result = await delete_client_resources(
        guild,
        guild.me,
        client=client,
        client_repo=context.store.clients,
        network_repo=context.store.networks,
        context=context,
    )

    assert result.success is True
    assert await context.store.clients.get_by_id(client.id) is None
    assert await context.store.clients.get_subscription(client.id, network.id) is None
    assert await context.store.clients.is_blacklisted(subscription.id, other_client.id) is False
    assert await context.store.clients.is_blacklisted(other_subscription.id, client.id) is False
    assert publish.delete.await_count >= 1
    assert subscribe.delete.await_count >= 1
    assert profile.delete.await_count >= 1
    category.delete.assert_awaited_once()
    client_role.delete.assert_awaited_once()
    context.refresh_projections.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_client_stops_when_unsubscribe_fails(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _make_context(db)
    network = await context.store.networks.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    client = await context.store.clients.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    await context.store.clients.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=203,
        subscribe_channel_id=202,
    )

    unsubscribe_result = MagicMock(success=False, error="Missing Permissions")
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.unsubscribe_client",
        AsyncMock(return_value=unsubscribe_result),
    )

    guild = MagicMock(spec=discord.Guild)
    guild.me = MagicMock(spec=discord.Member)

    result = await delete_client_resources(
        guild,
        guild.me,
        client=client,
        client_repo=context.store.clients,
        network_repo=context.store.networks,
        context=context,
    )

    assert result.success is False
    assert result.error == "Missing Permissions"
    assert await context.store.clients.get_by_id(client.id) is not None
    assert await context.store.clients.get_subscription(client.id, network.id) is not None
