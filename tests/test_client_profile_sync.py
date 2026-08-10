from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from view_registry_helpers import make_test_view_registry

from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.domain.network import Network
from bot.services.client_profile_sync import (
    build_moderation_embed,
    post_subscription_moderation_embed,
)
from bot.services.subscription_setup import SubscriptionSetupState


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


def _subscription(*, moderation_message_id: int | None = None) -> ClientSubscription:
    return ClientSubscription(
        id=5,
        client_id=1,
        network_id=2,
        network_key="stingers",
        publish_channel_id=201,
        subscribe_channel_id=501,
        moderation_message_id=moderation_message_id,
        publish_setup_message_id=None,
        subscribe_setup_message_id=None,
        activation_welcome_message_id=None,
        subscribe_confirmed=False,
        enabled=True,
    )


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
async def test_moderation_embed_posts_to_profile_channel() -> None:
    profile_channel = MagicMock(spec=discord.TextChannel)
    profile_channel.id = 30
    profile_channel.send = AsyncMock(
        return_value=MagicMock(spec=discord.Message, id=999)
    )
    profile_channel.fetch_message = AsyncMock()

    subscribe_channel = MagicMock(spec=discord.TextChannel)
    subscribe_channel.id = 501
    subscribe_channel.send = AsyncMock()

    guild = MagicMock(spec=discord.Guild)
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: (
            profile_channel if channel_id == 30 else subscribe_channel
        )
    )

    bot = MagicMock()
    bot.add_view = MagicMock()
    context = MagicMock()
    context.client_repo.update_moderation_message_id = AsyncMock()

    await post_subscription_moderation_embed(
        bot,
        context,
        guild,
        client=_client(),
        network=_network(),
        subscription=_subscription(),
        view_registry=make_test_view_registry(),
    )

    profile_channel.send.assert_awaited_once()
    subscribe_channel.send.assert_not_called()
    context.client_repo.update_moderation_message_id.assert_awaited_once_with(5, 999)


@pytest.mark.asyncio
async def test_moderation_embed_edits_prior_message_in_profile() -> None:
    profile_channel = MagicMock(spec=discord.TextChannel)
    profile_channel.id = 30
    prior = MagicMock(spec=discord.Message)
    prior.edit = AsyncMock()
    profile_channel.fetch_message = AsyncMock(return_value=prior)
    profile_channel.send = AsyncMock()

    guild = MagicMock(spec=discord.Guild)
    guild.get_channel = MagicMock(return_value=profile_channel)

    bot = MagicMock()
    bot.add_view = MagicMock()
    context = MagicMock()
    context.client_repo.update_moderation_message_id = AsyncMock()

    await post_subscription_moderation_embed(
        bot,
        context,
        guild,
        client=_client(),
        network=_network(),
        subscription=_subscription(moderation_message_id=888),
        view_registry=make_test_view_registry(),
    )

    profile_channel.fetch_message.assert_awaited_once_with(888)
    prior.edit.assert_awaited_once()
    prior.delete.assert_not_called()
    profile_channel.send.assert_not_called()
    context.client_repo.update_moderation_message_id.assert_not_called()


@pytest.mark.asyncio
async def test_moderation_embed_reconcile_skips_when_fully_configured() -> None:
    profile_channel = MagicMock(spec=discord.TextChannel)
    profile_channel.send = AsyncMock()
    profile_channel.fetch_message = AsyncMock()

    guild = MagicMock(spec=discord.Guild)
    guild.get_channel = MagicMock(return_value=profile_channel)

    bot = MagicMock()
    bot.add_view = MagicMock()
    context = MagicMock()

    await post_subscription_moderation_embed(
        bot,
        context,
        guild,
        client=_client(),
        network=_network(),
        subscription=_subscription(moderation_message_id=888),
        setup_state=SubscriptionSetupState(
            publish_configured=True,
            subscribe_confirmed=True,
            network_active=True,
        ),
        setup_mode="reconcile",
        view_registry=make_test_view_registry(),
    )

    profile_channel.send.assert_not_called()
    profile_channel.fetch_message.assert_not_called()


def test_moderation_setup_embed_points_at_instruction_cards() -> None:
    embed = build_moderation_embed(
        network_display_name="Stingers",
        network_key="stingers",
        client_server_name="acme",
        setup_state=SubscriptionSetupState(
            publish_configured=False,
            subscribe_confirmed=False,
            network_active=True,
        ),
        publish_mention="#publish",
        subscribe_mention="#subscribe",
    )
    setup_fields = {field.name: field.value for field in embed.fields}
    assert setup_fields["Publish setup"] == "Follow the instruction card in #publish."
    assert "instruction card in #subscribe" in setup_fields["Subscribe setup"]


def test_moderation_setup_embed_shows_both_steps_when_unconfigured() -> None:
    embed = build_moderation_embed(
        network_display_name="Stingers",
        network_key="stingers",
        client_server_name="acme",
        setup_state=SubscriptionSetupState(
            publish_configured=False,
            subscribe_confirmed=False,
            network_active=True,
        ),
        publish_mention="#publish",
        subscribe_mention="#subscribe",
    )
    field_names = {field.name for field in embed.fields}
    assert field_names == {
        "Publish channel",
        "Publish setup",
        "Subscribe channel",
        "Subscribe setup",
    }
    assert "Finish connecting" in (embed.description or "")


def test_moderation_setup_embed_hides_completed_publish_step() -> None:
    embed = build_moderation_embed(
        network_display_name="Stingers",
        network_key="stingers",
        client_server_name="acme",
        setup_state=SubscriptionSetupState(
            publish_configured=True,
            subscribe_confirmed=False,
            network_active=True,
        ),
        publish_mention="#publish",
        subscribe_mention="#subscribe",
    )
    field_names = {field.name for field in embed.fields}
    assert field_names == {"Subscribe channel", "Subscribe setup"}
    assert "subscribe" in (embed.description or "").lower()
    assert "publish" not in (embed.description or "").lower()


def test_moderation_setup_embed_hides_completed_subscribe_step() -> None:
    embed = build_moderation_embed(
        network_display_name="Stingers",
        network_key="stingers",
        client_server_name="acme",
        setup_state=SubscriptionSetupState(
            publish_configured=False,
            subscribe_confirmed=True,
            network_active=True,
        ),
        publish_mention="#publish",
        subscribe_mention="#subscribe",
    )
    field_names = {field.name for field in embed.fields}
    assert field_names == {"Publish channel", "Publish setup"}
    assert "publish" in (embed.description or "").lower()
    assert "subscribe" not in (embed.description or "").lower()


@pytest.mark.asyncio
async def test_deleted_network_shows_disabled_without_join_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from view_registry_helpers import make_test_view_registry

    from bot.services.client_profile_sync import refresh_client_profile_message

    profile_channel = MagicMock(spec=discord.TextChannel)
    profile_channel.id = 30
    message = MagicMock(spec=discord.Message)
    message.edit = AsyncMock()
    profile_channel.fetch_message = AsyncMock(return_value=message)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    guild.get_channel = MagicMock(return_value=profile_channel)

    detached = ClientSubscription(
        id=5,
        client_id=1,
        network_id=None,
        network_key="stingers",
        publish_channel_id=201,
        subscribe_channel_id=501,
        moderation_message_id=None,
        publish_setup_message_id=None,
        subscribe_setup_message_id=None,
        activation_welcome_message_id=None,
        subscribe_confirmed=False,
        enabled=True,
    )

    context = MagicMock()
    context.client_repo.list_subscriptions_by_client = AsyncMock(return_value=[detached])
    context.network_repo.get_by_id = AsyncMock(return_value=None)
    context.network_repo.list_all = AsyncMock(return_value=[])
    context.client_repo.get_by_id = AsyncMock(return_value=_client())

    bot = MagicMock()
    bot.add_view = MagicMock()

    await refresh_client_profile_message(
        bot, context, guild, _client(), view_registry=make_test_view_registry()
    )

    message.edit.assert_awaited_once()
    embed = message.edit.await_args.kwargs["embed"]
    view = message.edit.await_args.kwargs["view"]
    networks_field = next(f for f in embed.fields if f.name == "Subscribed networks")
    assert "`stingers` — Disabled" in networks_field.value
    join_labels = {
        child.label
        for child in view.children
        if isinstance(child, discord.ui.Button) and child.label.startswith("Join ")
    }
    assert join_labels == set()
