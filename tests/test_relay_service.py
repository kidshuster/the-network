from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.clients.cache import ClientCache
from bot.config import Settings
from bot.db.repositories import ClientRepository, NetworkRepository, RelayRecordRepository
from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.networks.routing import RoutingService
from bot.relay.service import RelayService


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    monkeypatch.setenv("MANUAL_RELAY_ENABLED", "false")
    return Settings(_env_file=None)


async def _seed_client_subscription(
    db,
    *,
    network_enabled: bool = True,
    client_enabled: bool = True,
    subscription_enabled: bool = True,
) -> tuple[Client, ClientSubscription, Client, ClientSubscription]:
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    if not network_enabled:
        await network_repo.set_enabled("stingers", False)

    client = await client_repo.create(
        guild_id=100,
        server_name="publisher",
        display_name="Publisher",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=client_enabled,
    )
    await client_repo.update_emoji_fields(
        client.id,
        emoji_id=888,
        emoji_name="net_publisher",
        image_hash="hash",
        degraded_reason=None,
    )
    client = await client_repo.get_by_id(client.id)
    assert client is not None

    subscriber = await client_repo.create(
        guild_id=100,
        server_name="subscriber",
        display_name="Subscriber",
        category_id=11,
        client_role_id=21,
        profile_channel_id=31,
        profile_message_id=41,
    )
    sub_pub = await client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=201,
        subscribe_channel_id=500,
        enabled=subscription_enabled,
    )
    sub_sub = await client_repo.create_subscription(
        client_id=subscriber.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=202,
        subscribe_channel_id=501,
    )
    return client, sub_pub, subscriber, sub_sub


def _make_webhook_message(
    *,
    message_id: int = 1001,
    channel_id: int = 201,
    content: str = "Raid starts at 8 PM.",
    author_name: str = "Original Username",
    webhook_id: int = 777,
) -> discord.Message:
    message = MagicMock(spec=discord.Message)
    message.id = message_id
    message.content = content
    message.webhook_id = webhook_id
    message.embeds = []
    message.attachments = []

    author = MagicMock()
    author.name = author_name
    author.display_name = author_name
    author.bot = False
    message.author = author

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    message.channel = channel

    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    message.guild = guild
    return message


async def _build_service(
    db,
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings | None = None,
) -> RelayService:
    settings = settings or _settings(monkeypatch)
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    relay_record_repo = RelayRecordRepository(db)
    routing = RoutingService(network_repo, client_repo)
    client_cache = ClientCache(client_repo)
    await client_cache.load_cache()
    routing.attach_client_cache(client_cache)
    await routing.load_cache()
    return RelayService(settings, routing, client_cache, client_repo, relay_record_repo)


@pytest.mark.asyncio
async def test_end_to_end_webhook_relay(db, monkeypatch: pytest.MonkeyPatch) -> None:
    _client, _sub, _subscriber, _sub_sub = await _seed_client_subscription(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()

    own_subscribe = MagicMock(spec=discord.TextChannel)
    own_sent = MagicMock(spec=discord.Message)
    own_sent.id = 9000
    own_sent.publish = AsyncMock()
    own_subscribe.send = AsyncMock(return_value=own_sent)

    other_subscribe = MagicMock(spec=discord.TextChannel)
    other_sent = MagicMock(spec=discord.Message)
    other_sent.id = 9001
    other_sent.publish = AsyncMock()
    other_subscribe.send = AsyncMock(return_value=other_sent)

    def _get_channel(channel_id: int) -> discord.TextChannel | None:
        if channel_id == 500:
            return own_subscribe
        if channel_id == 501:
            return other_subscribe
        return None

    message.guild.get_channel = MagicMock(side_effect=_get_channel)

    result = await service.relay_message(message)
    assert result is not None
    assert result.success
    assert result.destination_message_ids == (9000, 9001)
    own_subscribe.send.assert_awaited_once()
    other_subscribe.send.assert_awaited_once()
    own_sent.publish.assert_awaited_once()
    other_sent.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_self_relay_to_own_subscribe_channel(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    client = await client_repo.create(
        guild_id=100,
        server_name="solo",
        display_name="Solo",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
    )
    await client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=201,
        subscribe_channel_id=500,
    )

    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()

    output_channel = MagicMock(spec=discord.TextChannel)
    sent = MagicMock(spec=discord.Message)
    sent.id = 9001
    sent.publish = AsyncMock()
    output_channel.send = AsyncMock(return_value=sent)
    message.guild.get_channel = MagicMock(return_value=output_channel)

    result = await service.relay_message(message)
    assert result is not None
    assert result.success
    assert result.destination_message_ids == (9001,)
    output_channel.send.assert_awaited_once()
    sent.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_source_ignored(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_client_subscription(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()

    output_channel = MagicMock(spec=discord.TextChannel)
    sent = MagicMock(spec=discord.Message)
    sent.id = 9001
    sent.publish = AsyncMock()
    output_channel.send = AsyncMock(return_value=sent)
    message.guild.get_channel = MagicMock(return_value=output_channel)

    first = await service.relay_message(message)
    second = await service.relay_message(message)
    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_disabled_client_ignored(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_client_subscription(db, client_enabled=False)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()
    assert service.is_potential_feed_message(message) is False


@pytest.mark.asyncio
async def test_disabled_network_ignored(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_client_subscription(db, network_enabled=False)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()
    assert service._passes_filters(message) is False


@pytest.mark.asyncio
async def test_non_webhook_ignored_without_manual_relay(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_client_subscription(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message(webhook_id=0)
    assert service._passes_filters(message) is False


def _relay_channel_mocks(
    message: discord.Message,
    *,
    publisher_subscribe_id: int = 500,
    subscriber_subscribe_id: int = 501,
) -> tuple[MagicMock, MagicMock]:
    publisher_channel = MagicMock(spec=discord.TextChannel)
    publisher_sent = MagicMock(spec=discord.Message)
    publisher_sent.id = 9000
    publisher_sent.publish = AsyncMock()
    publisher_channel.send = AsyncMock(return_value=publisher_sent)

    subscriber_channel = MagicMock(spec=discord.TextChannel)
    subscriber_sent = MagicMock(spec=discord.Message)
    subscriber_sent.id = 9001
    subscriber_sent.publish = AsyncMock()
    subscriber_channel.send = AsyncMock(return_value=subscriber_sent)

    def _get_channel(channel_id: int) -> discord.TextChannel | None:
        if channel_id == publisher_subscribe_id:
            return publisher_channel
        if channel_id == subscriber_subscribe_id:
            return subscriber_channel
        return None

    message.guild.get_channel = MagicMock(side_effect=_get_channel)
    return publisher_channel, subscriber_channel


@pytest.mark.asyncio
async def test_blacklist_blocks_incoming_from_blocked_client(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a subscriber blacklists the publisher, they do not receive relays."""
    publisher, _pub_sub, _subscriber, sub_sub = await _seed_client_subscription(db)
    client_repo = ClientRepository(db)
    await client_repo.add_blacklist(sub_sub.id, publisher.id)

    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()
    publisher_channel, subscriber_channel = _relay_channel_mocks(message)

    result = await service.relay_message(message)
    assert result is not None
    assert result.success
    assert result.destination_message_ids == (9000,)
    publisher_channel.send.assert_awaited_once()
    subscriber_channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_blacklist_blocks_outgoing_to_blocked_client(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a publisher blacklists a subscriber, that subscriber is skipped."""
    publisher, pub_sub, subscriber, _sub_sub = await _seed_client_subscription(db)
    client_repo = ClientRepository(db)
    await client_repo.add_blacklist(pub_sub.id, subscriber.id)

    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()
    publisher_channel, subscriber_channel = _relay_channel_mocks(message)

    result = await service.relay_message(message)
    assert result is not None
    assert result.success
    assert result.destination_message_ids == (9000,)
    publisher_channel.send.assert_awaited_once()
    subscriber_channel.send.assert_not_awaited()
