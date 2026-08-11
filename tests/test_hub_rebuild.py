from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from context_helpers import make_test_context
from view_registry_helpers import make_test_view_registry

from bot.core.clients.subscription import resync_subscriptions_for_network
from bot.core.hub.data_reset import reset_hub_layout_data


@pytest.mark.asyncio
async def test_hub_rebuild_preserves_client_and_relinks_subscription(db, monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    context = make_test_context(db)

    guild_id = 100
    network = await context.store.networks.create(
        guild_id=guild_id,
        key="stingers",
        display_name="Stingers",
    )
    client = await context.store.clients.create(
        guild_id=guild_id,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    await context.store.clients.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=201,
        subscribe_channel_id=301,
    )

    await reset_hub_layout_data(context, guild_id)

    clients = await context.store.clients.list_all()
    assert len(clients) == 1
    assert clients[0].id == client.id
    assert await context.store.clients.list_subscriptions_by_client(client.id) == []
    assert await context.store.networks.list_all() == []

    network = await context.store.networks.create(
        guild_id=guild_id,
        key="stingers",
        display_name="Stingers",
    )

    publish = MagicMock(spec=discord.TextChannel)
    publish.id = 201
    publish.name = "stingers-publish"
    publish.edit = AsyncMock()
    publish.send = AsyncMock(return_value=MagicMock(id=888))
    subscribe = MagicMock(spec=discord.TextChannel)
    subscribe.id = 301
    subscribe.name = "stingers-subscribe"
    subscribe.edit = AsyncMock()
    subscribe.send = AsyncMock(return_value=MagicMock(id=889))
    profile = MagicMock(spec=discord.TextChannel)
    profile.id = 30
    profile.name = "network-profile"
    profile.fetch_message = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "missing"))
    profile.send = AsyncMock(return_value=MagicMock(id=888))

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.channels = [profile, subscribe, publish]

    client_role = MagicMock(spec=discord.Role)
    client_role.id = 11
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
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

    bot = MagicMock()
    bot.settings = MagicMock(network_access_role_name="The Network")
    bot.add_view = MagicMock()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "bot.core.clients.subscription.resolve_access_role",
            lambda *_args, **_kwargs: client_role,
        )
        patch.setattr(
            "bot.core.clients.subscription.resolve_human_moderator_role",
            lambda *_args, **_kwargs: None,
        )
        relinked = await resync_subscriptions_for_network(
            guild,
            bot,
            context,
            network,
            access_role_name="The Network",
            view_registry=make_test_view_registry(),
        )

    assert relinked == 1
    await context.routing_service.load_cache()
    await context.client_cache.load_cache()
    subs = await context.store.clients.list_subscriptions_by_client(client.id)
    assert len(subs) == 1
    assert subs[0].publish_channel_id == 201
    assert subs[0].subscribe_channel_id == 301
    assert subs[0].network_id == network.id
    assert context.routing_service.resolve_publish_subscription(201) is not None
