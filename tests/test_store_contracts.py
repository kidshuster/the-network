from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import pytest
from store_helpers import create_test_client, create_test_network, create_test_subscription

from bot.core.database.domains.resources import ManagedResource
from bot.core.database.errors import StoreConflict, StoreError
from bot.core.database.store import Store


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
        store.clients,
        guild_id=999,
        server_name="Other",
        category_id=91,
        client_role_id=92,
        profile_channel_id=93,
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
        store.clients,
        server_name="Blocked",
        category_id=41,
        client_role_id=42,
        profile_channel_id=43,
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
async def test_unrelated_write_waits_for_transaction_owner(db) -> None:
    store = Store.create(db)
    transaction_started = asyncio.Event()
    release_transaction = asyncio.Event()

    async def owner() -> None:
        async with db.transaction():
            await store.settings.set("owner", "1")
            transaction_started.set()
            await release_transaction.wait()

    async def unrelated() -> None:
        await transaction_started.wait()
        await store.settings.set("unrelated", "2")

    owner_task = asyncio.create_task(owner())
    unrelated_task = asyncio.create_task(unrelated())
    await transaction_started.wait()
    await asyncio.sleep(0)
    assert not unrelated_task.done()
    release_transaction.set()
    await asyncio.gather(owner_task, unrelated_task)
    assert await store.settings.get("owner") == "1"
    assert await store.settings.get("unrelated") == "2"


@pytest.mark.asyncio
async def test_network_delete_recipe_detaches_and_deletes_relations(db) -> None:
    store = Store.create(db)
    network = await create_test_network(store.networks)
    client = await create_test_client(store.clients)
    subscription = await create_test_subscription(store.clients, client=client, network=network)
    await store.relay.create_pending(
        source_message_id=777,
        source_channel_id=subscription.publish_channel_id,
        source_webhook_id=None,
        client_id=client.id,
        network_id=network.id,
        destination_channel_id=subscription.subscribe_channel_id,
    )
    request = await store.requests.create(
        guild_id=100,
        network_id=network.id,
        requester_user_id=22,
        server_name="Pending",
        display_name="Pending",
        profile_image_url="https://example.com/profile.png",
    )

    assert await store.networks.delete_with_relations(network.key) == network
    assert await store.networks.get_by_key(network.key) is None
    detached = await store.subscriptions.get_subscription_by_id(subscription.id)
    assert detached is not None and detached.network_id is None
    assert await store.relay.get_by_source_message(777) is None
    assert await store.requests.get_by_id(request.id) is None


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
        if "database" in path.relative_to(root).parts:
            continue
        source = path.read_text()
        if "bot.core.database.domains" in source or "import aiosqlite" in source:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
