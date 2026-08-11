from __future__ import annotations

import pytest
from store_helpers import create_test_network

from bot.constants import RelayStatus
from bot.db.store import NetworkStore, RelayStore
from bot.domain.errors import RelayError


@pytest.mark.asyncio
async def test_create_pending_and_exists(db) -> None:
    network_repo = NetworkStore(db)
    relay_repo = RelayStore(db)
    network = await create_test_network(network_repo)

    record = await relay_repo.create_pending(
        source_message_id=1000,
        source_channel_id=200,
        source_webhook_id=300,
        client_id=1,
        network_id=network.id,
        destination_channel_id=400,
    )
    assert record.status == RelayStatus.PENDING
    assert record.destination_message_ids == ()
    assert await relay_repo.exists(1000)
    assert await relay_repo.get_by_source_message(1000) == record


@pytest.mark.asyncio
async def test_create_pending_rejects_duplicate(db) -> None:
    network_repo = NetworkStore(db)
    relay_repo = RelayStore(db)
    network = await create_test_network(network_repo)

    await relay_repo.create_pending(
        source_message_id=1000,
        source_channel_id=200,
        source_webhook_id=None,
        network_id=network.id,
        destination_channel_id=400,
    )
    with pytest.raises(RelayError, match="already exists for message 1000"):
        await relay_repo.create_pending(
            source_message_id=1000,
            source_channel_id=201,
            source_webhook_id=None,
            network_id=network.id,
            destination_channel_id=401,
        )


@pytest.mark.asyncio
async def test_update_status_with_destination_ids(db) -> None:
    network_repo = NetworkStore(db)
    relay_repo = RelayStore(db)
    network = await create_test_network(network_repo)

    record = await relay_repo.create_pending(
        source_message_id=1000,
        source_channel_id=200,
        source_webhook_id=None,
        network_id=network.id,
        destination_channel_id=400,
    )
    updated = await relay_repo.update_status(
        record.id,
        status=RelayStatus.PUBLISHED,
        destination_message_ids=(500, 501),
        error_message=None,
    )
    assert updated.status == RelayStatus.PUBLISHED
    assert updated.destination_message_ids == (500, 501)


@pytest.mark.asyncio
async def test_delete_by_network_id(db) -> None:
    network_repo = NetworkStore(db)
    relay_repo = RelayStore(db)
    network = await create_test_network(network_repo)

    await relay_repo.create_pending(
        source_message_id=1000,
        source_channel_id=200,
        source_webhook_id=None,
        network_id=network.id,
        destination_channel_id=400,
    )
    await relay_repo.delete_by_network_id(network.id)
    assert not await relay_repo.exists(1000)
