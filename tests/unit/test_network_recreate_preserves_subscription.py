from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from context_helpers import make_test_context
from view_registry_helpers import make_test_view_registry

from bot.features.recipes.hub.clients.subscription import resync_subscriptions_for_network


def _guild_with_subscription_channels(
    *,
    guild_id: int,
    category_id: int,
    profile_id: int,
    publish_id: int,
    subscribe_id: int,
    role_id: int,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    publish = MagicMock(spec=discord.TextChannel)
    publish.id = publish_id
    publish.name = "acme-stingers-publish"
    publish.edit = AsyncMock()
    publish.send = AsyncMock()
    publish.webhooks = AsyncMock(return_value=[])

    subscribe = MagicMock(spec=discord.TextChannel)
    subscribe.id = subscribe_id
    subscribe.name = "acme-stingers-subscribe"
    subscribe.edit = AsyncMock()
    subscribe.send = AsyncMock()

    profile = MagicMock(spec=discord.TextChannel)
    profile.id = profile_id
    profile.name = "acme-profile"
    profile.fetch_message = AsyncMock(return_value=MagicMock(edit=AsyncMock()))
    profile.send = AsyncMock()

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = category_id
    category.channels = [profile, subscribe, publish]

    client_role = MagicMock(spec=discord.Role)
    client_role.id = role_id

    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.me = MagicMock(spec=discord.Member)
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {
            category_id: category,
            profile_id: profile,
            publish_id: publish,
            subscribe_id: subscribe,
        }.get(channel_id)
    )
    guild.get_role = MagicMock(return_value=client_role)
    return guild, publish, subscribe


@pytest.mark.asyncio
async def test_network_delete_recreate_preserves_setup_and_skips_welcomes(
    db, monkeypatch
) -> None:
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
    subscription = await context.store.clients.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=201,
        subscribe_channel_id=301,
    )
    subscription = await context.store.clients.set_subscribe_confirmed(
        subscription.id, True
    )
    subscription = await context.store.clients.update_activation_welcome_message_id(
        subscription.id, 111
    )
    subscription = await context.store.clients.update_network_welcome_message_id(
        subscription.id, 222
    )
    await context.store.clients.mark_network_welcome_complete(subscription.id)

    await context.store.networks.delete_with_relations("stingers")
    orphan = await context.store.clients.get_subscription_by_client_and_key(
        client.id, "stingers"
    )
    assert orphan is not None
    assert orphan.network_id is None
    assert orphan.subscribe_confirmed is True
    assert orphan.activation_welcome_message_id == 111
    assert orphan.network_welcome_complete is True

    network = await context.store.networks.create(
        guild_id=guild_id,
        key="stingers",
        display_name="Stingers",
    )
    guild, publish, subscribe = _guild_with_subscription_channels(
        guild_id=guild_id,
        category_id=10,
        profile_id=30,
        publish_id=201,
        subscribe_id=301,
        role_id=11,
    )
    follower = MagicMock()
    follower.type = discord.WebhookType.channel_follower
    publish.webhooks = AsyncMock(return_value=[follower])

    bot = MagicMock()
    bot.user = MagicMock(id=99)
    bot.settings = MagicMock(network_access_role_name="The Network")
    bot.add_view = MagicMock()

    welcome = AsyncMock()
    with (
        patch(
            "bot.features.recipes.hub.clients.subscription.resolve_access_role",
            lambda *_args, **_kwargs: guild.get_role(11),
        ),
        patch(
            "bot.features.recipes.hub.clients.subscription.resolve_human_moderator_role",
            lambda *_args, **_kwargs: None,
        ),
        patch(
            "bot.features.channels.stickies.subscription._maybe_post_activation_welcome",
            welcome,
        ),
        patch(
            "bot.features.channels.stickies.subscription.sync_footer_marker_embed_sticky",
            AsyncMock(
                return_value=MagicMock(message=None, removed=False, created=False),
            ),
        ),
    ):
        relinked = await resync_subscriptions_for_network(
            guild,
            bot,
            context,
            network,
            access_role_name="The Network",
            view_registry=make_test_view_registry(),
        )

    assert relinked == 1
    welcome.assert_not_awaited()
    subscribe.send.assert_not_awaited()

    subs = await context.store.clients.list_subscriptions_by_client(client.id)
    assert len(subs) == 1
    assert subs[0].network_id == network.id
    assert subs[0].subscribe_confirmed is True
    assert subs[0].activation_welcome_message_id == 111
    assert subs[0].network_welcome_message_id == 222
    assert subs[0].network_welcome_complete is True


@pytest.mark.asyncio
async def test_network_create_silently_adopts_zombie_channels(
    db, monkeypatch
) -> None:
    """After uninit wiped DB rows, surviving publish/subscribe channels reconnect quietly."""
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    context = make_test_context(db)

    guild_id = 100
    client = await context.store.clients.create(
        guild_id=guild_id,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    network = await context.store.networks.create(
        guild_id=guild_id,
        key="stingers",
        display_name="Stingers",
    )
    guild, publish, subscribe = _guild_with_subscription_channels(
        guild_id=guild_id,
        category_id=10,
        profile_id=30,
        publish_id=201,
        subscribe_id=301,
        role_id=11,
    )
    follower = MagicMock()
    follower.type = discord.WebhookType.channel_follower
    publish.webhooks = AsyncMock(return_value=[follower])

    bot = MagicMock()
    bot.user = MagicMock(id=99)
    bot.settings = MagicMock(network_access_role_name="The Network")
    bot.add_view = MagicMock()

    welcome = AsyncMock()
    sticky = AsyncMock(
        return_value=MagicMock(message=None, removed=True, created=False),
    )
    with (
        patch(
            "bot.features.recipes.hub.clients.subscription.resolve_access_role",
            lambda *_args, **_kwargs: guild.get_role(11),
        ),
        patch(
            "bot.features.recipes.hub.clients.subscription.resolve_human_moderator_role",
            lambda *_args, **_kwargs: None,
        ),
        patch(
            "bot.features.channels.stickies.subscription._maybe_post_activation_welcome",
            welcome,
        ),
        patch(
            "bot.features.channels.stickies.subscription.sync_footer_marker_embed_sticky",
            sticky,
        ),
    ):
        relinked = await resync_subscriptions_for_network(
            guild,
            bot,
            context,
            network,
            access_role_name="The Network",
            view_registry=make_test_view_registry(),
        )

    assert relinked == 1
    welcome.assert_not_awaited()
    subscribe.send.assert_not_awaited()

    subs = await context.store.clients.list_subscriptions_by_client(client.id)
    assert len(subs) == 1
    assert subs[0].subscribe_confirmed is True
    assert subs[0].activation_welcome_message_id == 0
    assert subs[0].network_welcome_complete is True
