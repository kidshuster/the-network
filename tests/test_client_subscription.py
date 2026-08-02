from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.db.repositories import ClientRepository, NetworkRepository
from bot.domain.client import Client
from bot.services.channel_names import (
    build_client_profile_channel_base,
    build_client_publish_channel_base,
    build_client_subscribe_channel_base,
    slugify_client_name,
)
from bot.services.client_subscription import (
    ClientSubscriptionService,
    build_client_category_channel_order,
    find_network_subscription_channels,
    reorder_client_category_channels,
    resync_subscriptions_for_network,
)
from bot.services.channel_names import LEGACY_CLIENT_PROFILE_CHANNEL


def _client(server_name: str = "acme") -> Client:
    return Client(
        id=1,
        guild_id=100,
        server_name=server_name,
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


def test_slugify_client_name() -> None:
    assert slugify_client_name("My Server") == "my-server"
    assert build_client_profile_channel_base("My Server") == "my-server-profile"
    assert build_client_publish_channel_base("My Server", "stingers") == (
        "my-server-stingers-publish"
    )
    assert build_client_subscribe_channel_base("My Server", "stingers") == (
        "my-server-stingers-subscribe"
    )


def test_build_client_category_channel_order_single_network() -> None:
    client = _client()
    assert build_client_category_channel_order(client, ["stingers"]) == [
        "acme-profile",
        LEGACY_CLIENT_PROFILE_CHANNEL,
        "acme-stingers-subscribe",
        "stingers-subscribe",
        "acme-stingers-publish",
        "stingers-publish",
    ]


def test_build_client_category_channel_order_sorts_network_keys() -> None:
    client = _client()
    assert build_client_category_channel_order(client, ["zebra", "alpha"]) == [
        "acme-profile",
        LEGACY_CLIENT_PROFILE_CHANNEL,
        "acme-alpha-subscribe",
        "alpha-subscribe",
        "acme-alpha-publish",
        "alpha-publish",
        "acme-zebra-subscribe",
        "zebra-subscribe",
        "acme-zebra-publish",
        "zebra-publish",
    ]


def test_find_network_subscription_channels_matches_new_and_legacy_names() -> None:
    category = MagicMock(spec=discord.CategoryChannel)
    publish = MagicMock(spec=discord.TextChannel)
    publish.name = "acme-stingers-publish"
    subscribe = MagicMock(spec=discord.TextChannel)
    subscribe.name = "acme-stingers-subscribe"
    other = MagicMock(spec=discord.TextChannel)
    other.name = "acme-profile"
    category.channels = [other, subscribe, publish]

    found_publish, found_subscribe = find_network_subscription_channels(
        category,
        "stingers",
        client=_client(),
    )
    assert found_publish is publish
    assert found_subscribe is subscribe


def test_find_network_subscription_channels_falls_back_to_legacy_names() -> None:
    category = MagicMock(spec=discord.CategoryChannel)
    publish = MagicMock(spec=discord.TextChannel)
    publish.name = "stingers-publish"
    subscribe = MagicMock(spec=discord.TextChannel)
    subscribe.name = "stingers-subscribe"
    category.channels = [subscribe, publish]

    found_publish, found_subscribe = find_network_subscription_channels(
        category,
        "stingers",
        client=_client(),
    )
    assert found_publish is publish
    assert found_subscribe is subscribe


@pytest.mark.asyncio
async def test_resync_subscriptions_for_network_links_existing_channels(db) -> None:
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    client = await client_repo.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )

    publish = MagicMock(spec=discord.TextChannel)
    publish.id = 201
    publish.name = "stingers-publish"
    publish.edit = AsyncMock()
    publish.webhooks = AsyncMock(return_value=[])
    publish.send = AsyncMock(return_value=MagicMock(id=9001))
    subscribe = MagicMock(spec=discord.TextChannel)
    subscribe.id = 301
    subscribe.name = "stingers-subscribe"
    subscribe.edit = AsyncMock()
    subscribe.send = AsyncMock(return_value=MagicMock(id=9002))
    profile = MagicMock(spec=discord.TextChannel)
    profile.id = 30
    profile.name = "network-profile"
    profile.fetch_message = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "missing"))
    profile.send = AsyncMock(return_value=MagicMock(id=999))

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.channels = [profile, subscribe, publish]
    category.edit = AsyncMock()

    client_role = MagicMock(spec=discord.Role)
    client_role.id = 11
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    guild.me = MagicMock(spec=discord.Member)
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {
            10: category,
            30: profile,
            201: publish,
            301: subscribe,
        }.get(channel_id)
    )
    guild.get_role = MagicMock(return_value=client_role)

    from bot.services.client_cache import ClientCache
    from bot.services.routing_service import RoutingService

    routing = RoutingService(network_repo, client_repo)
    client_cache = ClientCache(client_repo)
    routing.attach_client_cache(client_cache)
    context = MagicMock()
    context.db = db
    context.network_repo = network_repo
    context.client_repo = client_repo
    context.routing_service = routing
    context.client_cache = client_cache
    context.settings_repo = MagicMock()
    context.settings_repo.get = AsyncMock(return_value=None)
    context.settings_repo.set = AsyncMock()

    bot = MagicMock()
    bot.settings.network_access_role_name = "The Network"
    bot.add_view = MagicMock()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "bot.services.client_subscription.resolve_access_role",
            lambda *_args, **_kwargs: client_role,
        )
        patch.setattr(
            "bot.services.client_subscription.resolve_human_moderator_role",
            lambda *_args, **_kwargs: None,
        )
        relinked = await resync_subscriptions_for_network(
            guild,
            bot,
            context,
            network,
            access_role_name="The Network",
        )

    assert relinked == 1
    subs = await client_repo.list_subscriptions_by_client(client.id)
    assert len(subs) == 1
    assert subs[0].publish_channel_id == 201
    assert subs[0].subscribe_channel_id == 301
    assert subs[0].network_id == network.id


@pytest.mark.asyncio
async def test_reorder_client_category_channels_sets_positions(db) -> None:
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    client = await client_repo.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    await client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=203,
        subscribe_channel_id=202,
    )

    profile = MagicMock(spec=discord.TextChannel)
    profile.id = 30
    profile.name = "acme-profile"
    profile.edit = AsyncMock()

    subscribe = MagicMock(spec=discord.TextChannel)
    subscribe.id = 202
    subscribe.name = "acme-stingers-subscribe"
    subscribe.edit = AsyncMock()

    publish = MagicMock(spec=discord.TextChannel)
    publish.id = 203
    publish.name = "acme-stingers-publish"
    publish.edit = AsyncMock()

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.channels = [publish, profile, subscribe]

    await reorder_client_category_channels(
        category,
        client=client,
        client_repo=client_repo,
        network_repo=network_repo,
    )

    profile.edit.assert_awaited_once_with(
        position=0,
        reason="The Network client channel order",
    )
    subscribe.edit.assert_awaited_once_with(
        position=1,
        reason="The Network client channel order",
    )
    publish.edit.assert_awaited_once_with(
        position=2,
        reason="The Network client channel order",
    )


@pytest.mark.asyncio
async def test_unsubscribe_client_removes_subscription_and_channels(db) -> None:
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    client = await client_repo.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    subscription = await client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=203,
        subscribe_channel_id=202,
    )

    profile = MagicMock(spec=discord.TextChannel)
    profile.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
    publish = MagicMock(spec=discord.TextChannel)
    publish.webhooks = AsyncMock(return_value=[])
    publish.delete = AsyncMock()
    subscribe = MagicMock(spec=discord.TextChannel)
    subscribe.delete = AsyncMock()
    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.channels = [profile, subscribe, publish]

    guild = MagicMock(spec=discord.Guild)
    guild.me = MagicMock(spec=discord.Member)
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {
            30: profile,
            202: subscribe,
            203: publish,
            10: category,
        }.get(channel_id)
    )

    service = ClientSubscriptionService()
    result = await service.unsubscribe_client(
        guild,
        guild.me,
        client=client,
        subscription=subscription,
        network_key=network.key,
        client_repo=client_repo,
        network_repo=network_repo,
    )

    assert result.success is True
    assert await client_repo.get_subscription(client.id, network.id) is None
    publish.delete.assert_awaited_once()
    subscribe.delete.assert_awaited_once()
