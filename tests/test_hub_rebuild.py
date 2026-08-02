from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.client_subscription import resync_subscriptions_for_network
from bot.services.hub_data_reset import reset_hub_layout_data
from tests.test_hub_data_reset import _make_context


@pytest.mark.asyncio
async def test_hub_rebuild_preserves_client_and_relinks_subscription(db, monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    context = _make_context(db)

    guild_id = 100
    network = await context.network_repo.create(
        guild_id=guild_id,
        key="stingers",
        display_name="Stingers",
    )
    client = await context.client_repo.create(
        guild_id=guild_id,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    await context.client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=201,
        subscribe_channel_id=301,
    )

    await reset_hub_layout_data(context, guild_id)

    clients = await context.client_repo.list_all()
    assert len(clients) == 1
    assert clients[0].id == client.id
    assert await context.client_repo.list_subscriptions_by_client(client.id) == []
    assert await context.network_repo.list_all() == []

    network = await context.network_repo.create(
        guild_id=guild_id,
        key="stingers",
        display_name="Stingers",
    )

    publish = MagicMock(spec=discord.TextChannel)
    publish.id = 201
    publish.name = "stingers-publish"
    publish.edit = AsyncMock()
    subscribe = MagicMock(spec=discord.TextChannel)
    subscribe.id = 301
    subscribe.name = "stingers-subscribe"
    subscribe.edit = AsyncMock()
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
    await context.routing_service.load_cache()
    await context.client_cache.load_cache()
    subs = await context.client_repo.list_subscriptions_by_client(client.id)
    assert len(subs) == 1
    assert subs[0].publish_channel_id == 201
    assert subs[0].subscribe_channel_id == 301
    assert subs[0].network_id == network.id
    assert context.routing_service.resolve_publish_subscription(201) is not None
