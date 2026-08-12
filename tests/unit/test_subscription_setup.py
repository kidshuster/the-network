from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from view_registry_helpers import make_test_view_registry

from bot.core.clients.setup_state import (
    SubscriptionSetupState,
    derive_network_link_status,
    is_publish_configured,
)
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.network import Network
from bot.features.channels.stickies.subscription import (
    _find_setup_sticky_by_scan,
    _maybe_post_activation_welcome,
    _post_network_member_welcome,
    _sync_publish_setup_sticky,
    _sync_subscribe_setup_sticky,
)


@pytest.mark.asyncio
async def test_is_publish_configured_true_when_channel_follower_webhook() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    follower = MagicMock()
    follower.type = discord.WebhookType.channel_follower
    channel.webhooks = AsyncMock(return_value=[follower])

    assert await is_publish_configured(channel) is True


@pytest.mark.asyncio
async def test_is_publish_configured_false_without_follower_webhooks() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    incoming = MagicMock()
    incoming.type = discord.WebhookType.incoming
    channel.webhooks = AsyncMock(return_value=[incoming])

    assert await is_publish_configured(channel) is False


def test_derive_network_link_status() -> None:
    assert (
        derive_network_link_status(
            network_active=False,
            publish_configured=True,
            subscribe_confirmed=True,
        )
        == "Disabled"
    )
    assert (
        derive_network_link_status(
            network_active=True,
            publish_configured=False,
            subscribe_confirmed=True,
        )
        == "Not Configured"
    )
    assert (
        derive_network_link_status(
            network_active=True,
            publish_configured=True,
            subscribe_confirmed=False,
        )
        == "Not Configured"
    )
    assert (
        derive_network_link_status(
            network_active=True,
            publish_configured=True,
            subscribe_confirmed=True,
        )
        == "Active"
    )


def test_subscription_setup_state_fully_configured() -> None:
    state = SubscriptionSetupState(
        publish_configured=True,
        subscribe_confirmed=True,
        network_active=True,
    )
    assert state.fully_configured is True
    assert state.link_status == "Active"


def _client() -> Client:
    return Client(
        id=1,
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        timecode_enabled=True,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


def _subscription(**kwargs: object) -> ClientSubscription:
    defaults = dict(
        id=5,
        client_id=1,
        network_id=2,
        network_key="stingers",
        publish_channel_id=201,
        subscribe_channel_id=501,
        moderation_message_id=None,
        publish_setup_message_id=None,
        subscribe_setup_message_id=None,
        activation_welcome_message_id=None,
        network_welcome_message_id=None,
        network_welcome_complete=False,
        subscribe_confirmed=False,
        enabled=True,
    )
    defaults.update(kwargs)
    return ClientSubscription(**defaults)  # type: ignore[arg-type]


def _network() -> Network:
    return Network(
        id=2,
        key="stingers",
        display_name="Stingers",
        feed_category_id=None,
        output_channel_id=None,
        concat_channel_id=None,
        profile_forum_channel_id=None,
        enabled=True,
        join_channel_id=None,
    )


@pytest.mark.asyncio
async def test_reconcile_publish_sticky_creates_only_when_missing() -> None:
    publish_channel = MagicMock(spec=discord.TextChannel)
    publish_channel.id = 201
    publish_channel.mention = "#publish"
    publish_channel.send = AsyncMock(return_value=MagicMock(id=900))
    publish_channel.fetch_message = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
    publish_channel.history = MagicMock(return_value=_async_empty_history())

    guild = MagicMock(spec=discord.Guild)
    context = MagicMock()
    context.store.clients.update_publish_setup_message_id = AsyncMock(
        side_effect=lambda _sub_id, msg_id: _subscription(publish_setup_message_id=msg_id)
    )

    result = await _sync_publish_setup_sticky(
        guild,
        _subscription(),
        publish_channel=publish_channel,
        context=context,
        bot_user_id=999,
        configured=False,
        allow_create=False,
    )
    publish_channel.send.assert_not_called()
    assert result.publish_setup_message_id is None

    await _sync_publish_setup_sticky(
        guild,
        _subscription(),
        publish_channel=publish_channel,
        context=context,
        bot_user_id=999,
        configured=False,
        allow_create=True,
    )
    publish_channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_publish_sticky_refreshes_existing_message() -> None:
    publish_channel = MagicMock(spec=discord.TextChannel)
    publish_channel.id = 201
    publish_channel.mention = "#publish"
    publish_channel.send = AsyncMock()
    existing = MagicMock(spec=discord.Message)
    existing.id = 777
    existing.edit = AsyncMock()
    publish_channel.fetch_message = AsyncMock(return_value=existing)
    publish_channel.history = MagicMock(return_value=_async_empty_history())

    guild = MagicMock(spec=discord.Guild)
    context = MagicMock()
    context.store.clients.update_publish_setup_message_id = AsyncMock()

    await _sync_publish_setup_sticky(
        guild,
        _subscription(publish_setup_message_id=777),
        publish_channel=publish_channel,
        context=context,
        bot_user_id=999,
        configured=False,
        allow_create=False,
    )

    existing.edit.assert_awaited_once()
    publish_channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_find_setup_sticky_by_scan_adopts_orphaned_message() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    embed = MagicMock()
    embed.footer.text = "The Network • subscribe setup • removed after you confirm"
    message = MagicMock(spec=discord.Message)
    message.author.id = 42
    message.embeds = [embed]

    async def _history(**kwargs: object):
        yield message

    channel.history = MagicMock(return_value=_history())

    found = await _find_setup_sticky_by_scan(
        channel,
        bot_user_id=42,
        footer_marker="subscribe setup",
    )
    assert found is message


@pytest.mark.asyncio
async def test_reconcile_subscribe_sticky_does_not_create_new() -> None:
    subscribe_channel = MagicMock(spec=discord.TextChannel)
    subscribe_channel.id = 501
    subscribe_channel.mention = "#subscribe"
    subscribe_channel.send = AsyncMock()
    subscribe_channel.fetch_message = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
    subscribe_channel.history = MagicMock(return_value=_async_empty_history())

    guild = MagicMock(spec=discord.Guild)
    context = MagicMock()
    bot = MagicMock()
    bot.add_view = MagicMock()

    result = await _sync_subscribe_setup_sticky(
        guild,
        _subscription(),
        subscribe_channel=subscribe_channel,
        context=context,
        network=_network(),
        bot_user_id=999,
        confirmed=False,
        allow_create=False,
        view_registry=make_test_view_registry(),
    )

    subscribe_channel.send.assert_not_called()
    assert result.subscribe_setup_message_id is None


@pytest.mark.asyncio
async def test_activation_welcome_posts_once_when_fully_configured() -> None:
    subscribe_channel = MagicMock(spec=discord.TextChannel)
    subscribe_channel.id = 501
    sent_message = MagicMock(id=1001)
    sent_message.publish = AsyncMock()
    subscribe_channel.send = AsyncMock(return_value=sent_message)

    bot = MagicMock()
    bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/1/a.png"

    state = {"sub": _subscription()}

    async def _get_sub(_sid: int) -> ClientSubscription:
        return state["sub"]

    async def _update_activation(_sid: int, msg_id: int | None) -> ClientSubscription:
        state["sub"] = _subscription(activation_welcome_message_id=msg_id)
        return state["sub"]

    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(side_effect=_get_sub)
    context.store.clients.update_activation_welcome_message_id = AsyncMock(
        side_effect=_update_activation
    )
    context.store.clients.claim_network_welcome = AsyncMock(return_value=None)
    context.routing_service.list_network_subscriptions = MagicMock(return_value=[])

    guild = MagicMock()
    active_state = SubscriptionSetupState(
        publish_configured=True,
        subscribe_confirmed=True,
        network_active=True,
    )

    result = await _maybe_post_activation_welcome(
        bot,
        _subscription(),
        subscribe_channel=subscribe_channel,
        context=context,
        guild=guild,
        network=_network(),
        client=_client(),
        setup_state=active_state,
    )

    subscribe_channel.send.assert_awaited_once()
    sent_embed = subscribe_channel.send.await_args.kwargs["embed"]
    assert sent_embed.title == "Server connected — Stingers"
    assert sent_embed.author.icon_url == "https://cdn.discordapp.com/avatars/1/a.png"
    sent_message.publish.assert_awaited_once()
    assert result.activation_welcome_message_id == 1001


@pytest.mark.asyncio
async def test_network_member_welcome_posts_plain_text_to_network_announcements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = MagicMock()
    bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/1/a.png"

    message = MagicMock(spec=discord.Message)
    message.id = 4242
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock(return_value=message)
    guild = MagicMock()
    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(
        return_value=_subscription(activation_welcome_message_id=1),
    )
    context.store.clients.claim_network_welcome = AsyncMock(
        return_value=_subscription(
            activation_welcome_message_id=1,
            network_welcome_message_id=0,
        )
    )
    context.store.clients.update_network_welcome_message_id = AsyncMock(
        side_effect=lambda _sid, mid: _subscription(
            activation_welcome_message_id=1,
            network_welcome_message_id=mid,
        )
    )
    context.store.clients.mark_network_welcome_complete = AsyncMock(
        side_effect=lambda _sid: _subscription(
            activation_welcome_message_id=1,
            network_welcome_message_id=4242,
            network_welcome_complete=True,
        )
    )
    dispatch = AsyncMock(return_value=MagicMock(success=True, errors=()))
    monkeypatch.setattr(
        "bot.features.channels.stickies.subscription.resolve_hub_category",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "bot.features.channels.stickies.subscription.resolve_hub_channel",
        lambda *args, **kwargs: channel,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.announcements.dispatch_system_announcement",
        dispatch,
    )

    result = await _post_network_member_welcome(
        bot,
        context,
        guild,
        client=_client(),
        network=_network(),
        subscription=_subscription(activation_welcome_message_id=1),
    )

    channel.send.assert_awaited_once()
    kwargs = channel.send.await_args.kwargs
    assert "embed" not in kwargs or kwargs.get("embed") is None
    content = kwargs["content"]
    assert content.startswith("[stingers]")
    assert "acme" in content.casefold() or "Acme" in content
    dispatch.assert_awaited_once()
    assert dispatch.await_args.kwargs["exclude_client_id"] == 1
    assert dispatch.await_args.kwargs["about_client_id"] == 1
    assert result.network_welcome_complete is True


@pytest.mark.asyncio
async def test_network_welcome_retries_dispatch_without_reposting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = MagicMock()
    existing = MagicMock(spec=discord.Message)
    existing.id = 77
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=existing)
    channel.send = AsyncMock()
    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(
        return_value=_subscription(
            network_welcome_message_id=77,
            network_welcome_complete=False,
        )
    )
    context.store.clients.mark_network_welcome_complete = AsyncMock(
        return_value=_subscription(
            network_welcome_message_id=77,
            network_welcome_complete=True,
        )
    )
    dispatch = AsyncMock(return_value=MagicMock(success=True, errors=()))
    monkeypatch.setattr(
        "bot.features.channels.stickies.subscription.resolve_hub_category",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "bot.features.channels.stickies.subscription.resolve_hub_channel",
        lambda *args, **kwargs: channel,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.announcements.dispatch_system_announcement",
        dispatch,
    )

    result = await _post_network_member_welcome(
        bot,
        context,
        MagicMock(),
        client=_client(),
        network=_network(),
        subscription=_subscription(
            network_welcome_message_id=77,
            network_welcome_complete=False,
        ),
    )

    channel.send.assert_not_called()
    dispatch.assert_awaited_once()
    assert dispatch.await_args.args[2] is existing
    assert dispatch.await_args.kwargs["exclude_client_id"] == 1
    assert result.network_welcome_complete is True


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_activation_welcome_skips_when_not_fully_configured() -> None:
    subscribe_channel = MagicMock(spec=discord.TextChannel)
    subscribe_channel.send = AsyncMock()

    partial_state = SubscriptionSetupState(
        publish_configured=True,
        subscribe_confirmed=False,
        network_active=True,
    )

    await _maybe_post_activation_welcome(
        MagicMock(),
        _subscription(),
        subscribe_channel=subscribe_channel,
        context=MagicMock(),
        guild=MagicMock(),
        network=_network(),
        client=_client(),
        setup_state=partial_state,
    )

    subscribe_channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_activation_welcome_skips_local_when_already_sent_but_may_retry_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscribe_channel = MagicMock(spec=discord.TextChannel)
    subscribe_channel.send = AsyncMock()

    active_state = SubscriptionSetupState(
        publish_configured=True,
        subscribe_confirmed=True,
        network_active=True,
    )

    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(
        return_value=_subscription(
            activation_welcome_message_id=999,
            network_welcome_complete=True,
        ),
    )
    post_network = AsyncMock(
        return_value=_subscription(
            activation_welcome_message_id=999,
            network_welcome_complete=True,
        )
    )
    monkeypatch.setattr(
        "bot.features.channels.stickies.subscription._post_network_member_welcome",
        post_network,
    )

    await _maybe_post_activation_welcome(
        MagicMock(),
        _subscription(activation_welcome_message_id=999, network_welcome_complete=True),
        subscribe_channel=subscribe_channel,
        context=context,
        guild=MagicMock(),
        network=_network(),
        client=_client(),
        setup_state=active_state,
    )

    subscribe_channel.send.assert_not_called()
    post_network.assert_awaited_once()


def _async_empty_history():
    async def _history(**kwargs: object):
        if False:
            yield  # pragma: no cover

    return _history()
