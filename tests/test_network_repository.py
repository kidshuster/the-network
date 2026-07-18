from __future__ import annotations

import pytest

from bot.db.repositories import NetworkRepository
from bot.domain.errors import NetworkValidationError


@pytest.mark.asyncio
async def test_validate_key_normalizes_and_accepts(db) -> None:
    repo = NetworkRepository(db)
    assert repo.validate_key("Stingers") == "stingers"
    assert repo.validate_key("my-network_2") == "my-network_2"


@pytest.mark.asyncio
async def test_validate_key_rejects_invalid(db) -> None:
    repo = NetworkRepository(db)
    with pytest.raises(NetworkValidationError):
        repo.validate_key("2bad")
    with pytest.raises(NetworkValidationError):
        repo.validate_key("")


@pytest.mark.asyncio
async def test_create_and_get_by_key(db) -> None:
    repo = NetworkRepository(db)
    network = await repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers Network",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=201,
    )
    assert network.key == "stingers"
    assert network.display_name == "Stingers Network"
    assert network.enabled is True
    assert network.concat_channel_id == 201

    fetched = await repo.get_by_key("stingers")
    assert fetched == network


@pytest.mark.asyncio
async def test_create_rejects_duplicate_key(db) -> None:
    repo = NetworkRepository(db)
    await repo.create(
        guild_id=100,
        key="alpha",
        display_name="Alpha",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    with pytest.raises(NetworkValidationError, match="already exists"):
        await repo.create(
            guild_id=100,
            key="alpha",
            display_name="Alpha 2",
            feed_category_id=201,
            output_channel_id=301,
            concat_channel_id=None,
        )


@pytest.mark.asyncio
async def test_list_all_orders_by_key(db) -> None:
    repo = NetworkRepository(db)
    await repo.create(
        guild_id=100,
        key="zebra",
        display_name="Zebra",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    await repo.create(
        guild_id=100,
        key="alpha",
        display_name="Alpha",
        feed_category_id=201,
        output_channel_id=301,
        concat_channel_id=None,
    )
    keys = [n.key for n in await repo.list_all()]
    assert keys == ["alpha", "zebra"]


@pytest.mark.asyncio
async def test_set_enabled(db) -> None:
    repo = NetworkRepository(db)
    await repo.create(
        guild_id=100,
        key="beta",
        display_name="Beta",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    disabled = await repo.set_enabled("beta", False)
    assert disabled.enabled is False

    enabled = await repo.set_enabled("beta", True)
    assert enabled.enabled is True


@pytest.mark.asyncio
async def test_set_enabled_missing_key(db) -> None:
    repo = NetworkRepository(db)
    with pytest.raises(NetworkValidationError, match="not found"):
        await repo.set_enabled("missing", True)


@pytest.mark.asyncio
async def test_network_delete(db) -> None:
    repo = NetworkRepository(db)
    await repo.create(
        guild_id=100,
        key="gamma",
        display_name="Gamma",
        feed_category_id=555,
        output_channel_id=300,
        concat_channel_id=None,
    )
    deleted = await repo.delete("gamma")
    assert deleted.key == "gamma"
    assert await repo.get_by_key("gamma") is None


@pytest.mark.asyncio
async def test_network_delete_missing(db) -> None:
    repo = NetworkRepository(db)
    with pytest.raises(NetworkValidationError, match="not found"):
        await repo.delete("missing")


@pytest.mark.asyncio
async def test_get_by_feed_category(db) -> None:
    repo = NetworkRepository(db)
    await repo.create(
        guild_id=100,
        key="gamma",
        display_name="Gamma",
        feed_category_id=555,
        output_channel_id=300,
        concat_channel_id=None,
    )
    network = await repo.get_by_feed_category(555)
    assert network is not None
    assert network.key == "gamma"
