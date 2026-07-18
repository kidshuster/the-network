from __future__ import annotations

import pytest

from bot.db.repositories import NetworkRepository
from bot.domain.errors import RoutingError
from bot.services.routing_service import RoutingService


@pytest.mark.asyncio
async def test_load_cache_indexes_networks(db) -> None:
    repo = NetworkRepository(db)
    await repo.create(
        guild_id=100,
        key="net-a",
        display_name="Net A",
        feed_category_id=10,
        output_channel_id=20,
        concat_channel_id=None,
    )
    await repo.create(
        guild_id=100,
        key="net-b",
        display_name="Net B",
        feed_category_id=11,
        output_channel_id=21,
        concat_channel_id=22,
    )

    routing = RoutingService(repo)
    await routing.load_cache()

    assert routing.network_count == 2
    assert routing.get_by_key("net-a") is not None
    assert routing.get_by_category(11) is not None
    assert routing.get_by_category(999) is None


@pytest.mark.asyncio
async def test_resolve_category_route_respects_enabled(db) -> None:
    repo = NetworkRepository(db)
    await repo.create(
        guild_id=100,
        key="route-me",
        display_name="Route Me",
        feed_category_id=42,
        output_channel_id=99,
        concat_channel_id=43,
    )
    await repo.set_enabled("route-me", False)

    routing = RoutingService(repo)
    await routing.load_cache()

    assert routing.resolve_category_route(42) is None

    await repo.set_enabled("route-me", True)
    await routing.load_cache()

    route = routing.resolve_category_route(42)
    assert route is not None
    assert route.output_channel_id == 99
    assert route.concat_channel_id == 43


@pytest.mark.asyncio
async def test_resolve_source_channel_uses_parent_category(db) -> None:
    repo = NetworkRepository(db)
    await repo.create(
        guild_id=100,
        key="parent",
        display_name="Parent",
        feed_category_id=77,
        output_channel_id=88,
        concat_channel_id=None,
    )

    routing = RoutingService(repo)
    await routing.load_cache()

    route = routing.resolve_source_channel(channel_id=501, parent_id=77)
    assert route is not None
    assert route.network.key == "parent"

    assert routing.resolve_source_channel(channel_id=501, parent_id=None) is None


@pytest.mark.asyncio
async def test_require_by_key_raises_when_missing(db) -> None:
    routing = RoutingService(NetworkRepository(db))
    await routing.load_cache()
    with pytest.raises(RoutingError):
        routing.require_by_key("nope")
