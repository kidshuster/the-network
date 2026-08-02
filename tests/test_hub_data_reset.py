from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bot.context import BotContext
from bot.db.repositories import (
    ClientRepository,
    NetworkRepository,
    RelayRecordRepository,
    ServerRequestRepository,
    SettingsRepository,
)
from bot.services.client_cache import ClientCache
from bot.services.hub_data_reset import reset_hub_layout_data
from bot.services.join_requests_sticky import HOW_TO_JOIN_SETTINGS_KEY
from bot.services.network_admin_sticky import NETWORK_ADMIN_SETTINGS_KEY
from bot.services.routing_service import RoutingService


def _make_context(db) -> BotContext:
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    relay_record_repo = RelayRecordRepository(db)
    settings_repo = SettingsRepository(db)
    server_request_repo = ServerRequestRepository(db)
    routing = RoutingService(network_repo, client_repo)
    client_cache = ClientCache(client_repo)
    routing.attach_client_cache(client_cache)
    return BotContext.create(
        settings=MagicMock(),
        db=db,
        network_repo=network_repo,
        client_repo=client_repo,
        relay_record_repo=relay_record_repo,
        routing_service=routing,
        client_cache=client_cache,
        relay_service=MagicMock(),
        bot_settings=MagicMock(),
        settings_repo=settings_repo,
        server_request_repo=server_request_repo,
    )


@pytest.mark.asyncio
async def test_reset_hub_layout_data_clears_networks_but_preserves_clients(db) -> None:
    guild_id = 100
    other_guild_id = 200
    context = _make_context(db)

    network = await context.network_repo.create(
        guild_id=guild_id,
        key="stingers",
        display_name="Stingers",
    )
    await context.network_repo.create(
        guild_id=other_guild_id,
        key="other-net",
        display_name="Other",
    )
    client = await context.client_repo.create(
        guild_id=guild_id,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=12,
        profile_message_id=13,
    )
    subscription = await context.client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=201,
        subscribe_channel_id=301,
    )
    await context.client_repo.add_blacklist(subscription.id, client.id)
    await context.relay_record_repo.create_pending(
        source_message_id=9001,
        source_channel_id=201,
        source_webhook_id=None,
        client_id=client.id,
        network_id=network.id,
        destination_channel_id=401,
    )
    await context.server_request_repo.create(
        guild_id=guild_id,
        network_id=network.id,
        requester_user_id=555,
        server_name="pending",
        display_name="Pending",
        profile_image_url="https://example.com/a.png",
    )
    await context.settings_repo.set(NETWORK_ADMIN_SETTINGS_KEY, "1:99")
    await context.settings_repo.set(HOW_TO_JOIN_SETTINGS_KEY, "2:88")

    await context.routing_service.load_cache()
    await context.client_cache.load_cache()
    assert context.routing_service.network_count == 2
    assert context.client_cache.client_count == 1

    result = await reset_hub_layout_data(context, guild_id)

    assert result.networks_deleted == 1
    assert result.clients_deleted == 0
    assert result.subscriptions_deleted == 1
    assert result.server_requests_deleted == 1
    assert result.relay_records_deleted == 1
    assert result.blacklists_deleted == 1
    assert "clients preserved" in (result.summary_note() or "")

    remaining_clients = await context.client_repo.list_all()
    assert len(remaining_clients) == 1
    assert remaining_clients[0].id == client.id
    assert await context.client_repo.list_subscriptions_by_client(client.id) == []

    remaining_networks = await context.network_repo.list_all()
    assert len(remaining_networks) == 1
    assert remaining_networks[0].key == "other-net"
    assert await context.settings_repo.get(NETWORK_ADMIN_SETTINGS_KEY) is None

    assert context.routing_service.network_count == 1
    assert context.client_cache.client_count == 1
    assert context.client_count == 1


@pytest.mark.asyncio
async def test_reset_hub_layout_data_noop_when_guild_empty(db) -> None:
    context = _make_context(db)
    result = await reset_hub_layout_data(context, 999)
    assert result.summary_note() is None
    assert context.routing_service.network_count == 0
