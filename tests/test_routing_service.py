from __future__ import annotations

import pytest

from bot.clients.cache import ClientCache
from bot.db.store import ClientStore, NetworkStore
from bot.domain.errors import RoutingError
from bot.networks.routing import RoutingService


@pytest.mark.asyncio
async def test_load_cache_indexes_networks(db) -> None:
    repo = NetworkStore(db)
    await repo.create(guild_id=100, key="net-a", display_name="Net A")
    await repo.create(guild_id=100, key="net-b", display_name="Net B")

    routing = RoutingService(repo)
    await routing.load_cache()

    assert routing.network_count == 2
    assert routing.get_by_key("net-a") is not None
    assert routing.get_by_key("missing") is None


@pytest.mark.asyncio
async def test_resolve_publish_subscription(db) -> None:
    network_repo = NetworkStore(db)
    client_repo = ClientStore(db)
    network = await network_repo.create(guild_id=100, key="route-me", display_name="Route Me")
    client = await client_repo.create(
        guild_id=100,
        server_name="c1",
        display_name="C1",
        category_id=1,
        client_role_id=2,
        profile_channel_id=3,
        profile_message_id=4,
    )
    await client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=201,
        subscribe_channel_id=301,
    )

    routing = RoutingService(network_repo, client_repo)
    cache = ClientCache(client_repo)
    await cache.load_cache()
    routing.attach_client_cache(cache)
    await routing.load_cache()

    sub = routing.resolve_publish_subscription(201)
    assert sub is not None
    assert sub.publish_channel_id == 201
    assert routing.resolve_publish_subscription(999) is None


@pytest.mark.asyncio
async def test_require_by_key_raises_when_missing(db) -> None:
    routing = RoutingService(NetworkStore(db))
    await routing.load_cache()
    with pytest.raises(RoutingError):
        routing.require_by_key("nope")
