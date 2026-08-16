from __future__ import annotations

import pytest
from store_helpers import create_test_client, create_test_network, create_test_subscription

from bot.core.database.store import ClientStore, NetworkStore
from bot.core.models.errors import ProfileValidationError


@pytest.mark.asyncio
async def test_create_and_get_by_id(db) -> None:
    repo = ClientStore(db)
    client = await create_test_client(repo)
    fetched = await repo.get_by_id(client.id)
    assert fetched == client
    assert fetched is not None
    assert fetched.server_name == "Acme"
    assert fetched.enabled is True


@pytest.mark.asyncio
async def test_create_rejects_duplicate_server_name(db) -> None:
    repo = ClientStore(db)
    await create_test_client(repo, server_name="Acme")
    with pytest.raises(ProfileValidationError, match="already exists"):
        await create_test_client(
            repo,
            server_name="Acme",
            category_id=11,
            client_role_id=21,
            profile_channel_id=31,
            profile_message_id=41,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lookup", "expected_name"),
    [
        ("acme", "Acme"),
        ("ACME", "Acme"),
    ],
)
async def test_get_by_server_name_case_insensitive(db, lookup: str, expected_name: str) -> None:
    repo = ClientStore(db)
    await create_test_client(repo, server_name="Acme")
    fetched = await repo.get_by_server_name(100, lookup)
    assert fetched is not None
    assert fetched.server_name == expected_name


@pytest.mark.asyncio
async def test_get_by_server_name_empty_returns_none(db) -> None:
    repo = ClientStore(db)
    assert await repo.get_by_server_name(100, "  ") is None


@pytest.mark.asyncio
async def test_get_by_profile_channel(db) -> None:
    repo = ClientStore(db)
    client = await create_test_client(repo, profile_channel_id=777)
    fetched = await repo.get_by_profile_channel(777)
    assert fetched == client


@pytest.mark.asyncio
async def test_list_all_orders_by_server_name(db) -> None:
    repo = ClientStore(db)
    await create_test_client(
        repo, server_name="Zebra", category_id=11, client_role_id=21, profile_channel_id=31
    )
    await create_test_client(
        repo, server_name="Alpha", category_id=12, client_role_id=22, profile_channel_id=32
    )
    names = [c.server_name for c in await repo.list_all()]
    assert names == ["Alpha", "Zebra"]


@pytest.mark.asyncio
async def test_update_display_name_rejects_empty(db) -> None:
    repo = ClientStore(db)
    client = await create_test_client(repo)
    with pytest.raises(ProfileValidationError, match="Display name cannot be empty"):
        await repo.update_display_name(client.id, "  ")


@pytest.mark.asyncio
async def test_update_display_name_and_emoji_fields(db) -> None:
    repo = ClientStore(db)
    client = await create_test_client(repo)
    renamed = await repo.update_display_name(client.id, "New Name")
    assert renamed.display_name == "New Name"

    with_emoji = await repo.update_emoji_fields(
        client.id,
        emoji_id=99,
        emoji_name="acme_emoji",
        image_hash="abc123",
        degraded_reason=None,
    )
    assert with_emoji.emoji_id == 99
    assert with_emoji.emoji_name == "acme_emoji"


@pytest.mark.asyncio
async def test_set_enabled_and_timecode_enabled(db) -> None:
    repo = ClientStore(db)
    client = await create_test_client(repo)
    disabled = await repo.set_enabled(client.id, False)
    assert disabled.enabled is False
    no_timecodes = await repo.set_timecode_enabled(client.id, False)
    assert no_timecodes.timecode_enabled is False


@pytest.mark.asyncio
async def test_set_read_only_and_nullable_publish_channel(db) -> None:
    client_repo = ClientStore(db)
    network_repo = NetworkStore(db)
    network = await create_test_network(network_repo)
    client = await create_test_client(client_repo)
    updated = await client_repo.set_read_only(client.id, True)
    assert updated.read_only is True

    sub = await client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=None,
        subscribe_channel_id=501,
    )
    assert sub.publish_channel_id is None
    cleared = await client_repo.update_publish_channel_id(sub.id, None)
    assert cleared.publish_channel_id is None
    restored = await client_repo.update_publish_channel_id(sub.id, 999)
    assert restored.publish_channel_id == 999
    assert await client_repo.get_subscription_by_publish_channel(0) is None


@pytest.mark.asyncio
async def test_delete_returns_deleted_or_none(db) -> None:
    repo = ClientStore(db)
    client = await create_test_client(repo)
    deleted = await repo.delete(client.id)
    assert deleted == client
    assert await repo.get_by_id(client.id) is None
    assert await repo.delete(client.id) is None


@pytest.mark.asyncio
async def test_create_subscription_and_lookups(db) -> None:
    client_repo = ClientStore(db)
    network_repo = NetworkStore(db)
    network = await create_test_network(network_repo)
    client = await create_test_client(client_repo)
    sub = await create_test_subscription(client_repo, client=client, network=network)

    assert sub.network_key == "stingers"
    assert await client_repo.get_subscription_by_id(sub.id) == sub
    assert await client_repo.get_subscription(client.id, network.id) == sub
    assert await client_repo.get_subscription_by_client_and_key(client.id, "STINGERS") == sub
    assert await client_repo.get_subscription_by_publish_channel(100) == sub
    assert len(await client_repo.list_subscriptions_by_network(network.id)) == 1
    assert len(await client_repo.list_subscriptions_by_client(client.id)) == 1
    assert sub in await client_repo.list_all_subscriptions()


@pytest.mark.asyncio
async def test_create_subscription_rejects_duplicate(db) -> None:
    client_repo = ClientStore(db)
    network_repo = NetworkStore(db)
    network = await create_test_network(network_repo)
    client = await create_test_client(client_repo)
    await create_test_subscription(client_repo, client=client, network=network)
    with pytest.raises(ProfileValidationError, match="already subscribed"):
        await create_test_subscription(
            client_repo,
            client=client,
            network=network,
            publish_channel_id=102,
            subscribe_channel_id=103,
        )


@pytest.mark.asyncio
async def test_detach_and_relink_subscription(db) -> None:
    client_repo = ClientStore(db)
    network_repo = NetworkStore(db)
    network = await create_test_network(network_repo)
    client = await create_test_client(client_repo)
    sub = await create_test_subscription(client_repo, client=client, network=network)

    await client_repo.detach_subscriptions_from_network(network.id, network.key)
    detached = await client_repo.get_subscription_by_id(sub.id)
    assert detached is not None
    assert detached.network_id is None
    assert detached.network_key == "stingers"

    relinked = await client_repo.relink_subscription(sub.id, network.id)
    assert relinked.network_id == network.id


@pytest.mark.asyncio
async def test_subscription_message_id_updates(db) -> None:
    client_repo = ClientStore(db)
    network_repo = NetworkStore(db)
    network = await create_test_network(network_repo)
    client = await create_test_client(client_repo)
    sub = await create_test_subscription(client_repo, client=client, network=network)

    updated = await client_repo.update_moderation_message_id(sub.id, 900)
    assert updated.moderation_message_id == 900

    confirmed = await client_repo.set_subscribe_confirmed(sub.id, True)
    assert confirmed.subscribe_confirmed is True

    publish_setup = await client_repo.update_publish_setup_message_id(sub.id, 901)
    assert publish_setup.publish_setup_message_id == 901

    subscribe_setup = await client_repo.update_subscribe_setup_message_id(sub.id, 902)
    assert subscribe_setup.subscribe_setup_message_id == 902

    welcome = await client_repo.update_activation_welcome_message_id(sub.id, 903)
    assert welcome.activation_welcome_message_id == 903


@pytest.mark.asyncio
async def test_blacklist_idempotent_and_symmetric_relay_block(db) -> None:
    client_repo = ClientStore(db)
    network_repo = NetworkStore(db)
    network = await create_test_network(network_repo)
    client_a = await create_test_client(
        client_repo,
        server_name="Alpha",
        category_id=11,
        client_role_id=21,
        profile_channel_id=31,
    )
    client_b = await create_test_client(
        client_repo,
        server_name="Beta",
        category_id=12,
        client_role_id=22,
        profile_channel_id=32,
    )
    sub_a = await create_test_subscription(
        client_repo,
        client=client_a,
        network=network,
        publish_channel_id=110,
        subscribe_channel_id=111,
    )

    await client_repo.add_blacklist(sub_a.id, client_b.id)
    await client_repo.add_blacklist(sub_a.id, client_b.id)  # idempotent

    assert await client_repo.is_blacklisted(sub_a.id, client_b.id)
    assert client_b.id in await client_repo.list_blacklisted_client_ids(sub_a.id)
    sub_b = await create_test_subscription(
        client_repo,
        client=client_b,
        network=network,
        publish_channel_id=120,
        subscribe_channel_id=121,
    )
    assert await client_repo.is_relay_blocked(
        publisher_subscription_id=sub_a.id,
        publisher_client_id=client_a.id,
        destination_subscription_id=sub_b.id,
        destination_client_id=client_b.id,
    )

    await client_repo.remove_blacklist(sub_a.id, client_b.id)
    assert not await client_repo.is_blacklisted(sub_a.id, client_b.id)
