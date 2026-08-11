from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest
from store_helpers import create_test_client, create_test_network, create_test_subscription

from bot.db.domains.resources import ManagedResource
from bot.db.errors import StoreConflict, StoreError
from bot.db.store import Store


@pytest.mark.asyncio
async def test_store_shares_the_client_relation_boundary(db) -> None:
    store = Store.create(db)
    assert store.clients is store.subscriptions
    assert store.clients is store.blacklists


@pytest.mark.asyncio
async def test_layout_snapshot_is_guild_scoped(db) -> None:
    store = Store.create(db)
    network = await create_test_network(store.networks)
    client = await create_test_client(store.clients)
    subscription = await create_test_subscription(store.clients, client=client, network=network)
    await create_test_client(
        store.clients, guild_id=999, server_name="Other", category_id=91,
        client_role_id=92, profile_channel_id=93,
    )
    resource = ManagedResource(100, "client.custom.category", "category", 9876, "client", client.id)
    await store.resources.upsert(resource)

    snapshot = await store.layout.load_state(100)
    assert snapshot.clients == (client,)
    assert snapshot.subscriptions == (subscription,)
    assert resource in snapshot.resources


@pytest.mark.asyncio
async def test_resource_conflict_is_a_stable_store_error(db) -> None:
    store = Store.create(db)
    first = ManagedResource(100, "first", "channel", 55)
    await store.resources.upsert(first)
    with pytest.raises(StoreConflict, match="already registered") as raised:
        await store.resources.upsert(ManagedResource(100, "second", "channel", 55))
    assert isinstance(raised.value, StoreError)
    assert await store.resources.get(100, "first") == first


async def _related_client_data(store: Store):
    network = await create_test_network(store.networks)
    client = await create_test_client(store.clients)
    blocked = await create_test_client(
        store.clients, server_name="Blocked", category_id=41,
        client_role_id=42, profile_channel_id=43,
    )
    subscription = await create_test_subscription(store.clients, client=client, network=network)
    await store.blacklists.add_blacklist(subscription.id, blocked.id)
    return client, blocked, subscription


@pytest.mark.asyncio
async def test_client_delete_recipe_removes_relations_atomically(db) -> None:
    store = Store.create(db)
    client, blocked, subscription = await _related_client_data(store)
    await store.resources.upsert(
        ManagedResource(100, "client.test", "category", 9001, "client", client.id)
    )
    await store.resources.upsert(
        ManagedResource(100, "subscription.test", "channel", 9002, "subscription", subscription.id)
    )
    assert await store.clients.delete_with_relations(client.id) == client
    assert await store.clients.get_by_id(client.id) is None
    assert await store.subscriptions.get_subscription_by_id(subscription.id) is None
    assert await store.blacklists.is_blacklisted(subscription.id, blocked.id) is False
    assert await store.resources.get(100, "client.test") is None
    assert await store.resources.get(100, "subscription.test") is None


@pytest.mark.asyncio
async def test_nested_transaction_fails_immediately_instead_of_deadlocking(db) -> None:
    with pytest.raises(RuntimeError, match="Nested database transactions"):
        async with db.transaction():
            async with db.transaction():
                pytest.fail("nested transaction unexpectedly started")


@pytest.mark.asyncio
async def test_client_delete_recipe_rolls_back_on_failure(db) -> None:
    store = Store.create(db)
    client, blocked, subscription = await _related_client_data(store)
    await db.connection.execute(
        f"CREATE TRIGGER reject_client_delete BEFORE DELETE ON clients "
        f"WHEN OLD.id = {client.id} BEGIN SELECT RAISE(ABORT, 'test failure'); END"
    )
    await db.connection.commit()
    with pytest.raises(aiosqlite.IntegrityError, match="test failure"):
        await store.clients.delete_with_relations(client.id)
    assert await store.clients.get_by_id(client.id) == client
    assert await store.subscriptions.get_subscription_by_id(subscription.id) == subscription
    assert await store.blacklists.is_blacklisted(subscription.id, blocked.id) is True


def test_application_code_uses_store_boundary() -> None:
    root = Path(__file__).parents[1] / "bot"
    offenders = []
    for path in root.rglob("*.py"):
        if "db" in path.relative_to(root).parts:
            continue
        source = path.read_text()
        if "bot.db.domains" in source or "import aiosqlite" in source:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
