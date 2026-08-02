from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.context import BotContext
from bot.db.repositories import ClientRepository, NetworkRepository
from bot.services.client_cache import ClientCache
from bot.services.client_deletion import ClientDeletionService
from bot.services.routing_service import RoutingService
from bot.ui.network_views import NetworkProfileView


def _make_context(db) -> BotContext:
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    routing = RoutingService(network_repo, client_repo)
    client_cache = ClientCache(client_repo)
    routing.attach_client_cache(client_cache)
    return BotContext.create(
        settings=MagicMock(),
        db=db,
        network_repo=network_repo,
        client_repo=client_repo,
        relay_record_repo=MagicMock(),
        routing_service=routing,
        client_cache=client_cache,
        relay_service=MagicMock(),
        bot_settings=MagicMock(),
        settings_repo=MagicMock(),
        server_request_repo=MagicMock(),
    )


def test_network_profile_view_has_edit_and_delete_buttons() -> None:
    bot = MagicMock()
    view = NetworkProfileView(bot, client_id=1, network_keys=["stingers"])
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert "Edit Profile" in labels
    assert "Delete Client" in labels


@pytest.mark.asyncio
async def test_delete_client_removes_subscriptions_blacklists_and_client(db) -> None:
    context = _make_context(db)
    network = await context.network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    client = await context.client_repo.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    other_client = await context.client_repo.create(
        guild_id=100,
        server_name="beta",
        display_name="Beta",
        category_id=20,
        client_role_id=21,
        profile_channel_id=31,
        profile_message_id=41,
    )
    subscription = await context.client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        publish_channel_id=203,
        subscribe_channel_id=202,
    )
    other_subscription = await context.client_repo.create_subscription(
        client_id=other_client.id,
        network_id=network.id,
        publish_channel_id=303,
        subscribe_channel_id=302,
    )
    await context.client_repo.add_blacklist(subscription.id, other_client.id)
    await context.client_repo.add_blacklist(other_subscription.id, client.id)

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

    context.refresh_client_counts = AsyncMock()
    context.routing_service.load_cache = AsyncMock()

    service = ClientDeletionService()
    result = await service.delete_client(
        guild,
        guild.me,
        client=client,
        client_repo=context.client_repo,
        network_repo=context.network_repo,
        context=context,
    )

    assert result.success is True
    assert await context.client_repo.get_by_id(client.id) is None
    assert await context.client_repo.get_subscription(client.id, network.id) is None
    assert await context.client_repo.is_blacklisted(subscription.id, other_client.id) is False
    assert await context.client_repo.is_blacklisted(other_subscription.id, client.id) is False
    assert publish.delete.await_count >= 1
    assert subscribe.delete.await_count >= 1
    assert profile.delete.await_count >= 1
    category.delete.assert_awaited_once()
    client_role.delete.assert_awaited_once()
    context.refresh_client_counts.assert_awaited_once()
    context.routing_service.load_cache.assert_awaited_once()
