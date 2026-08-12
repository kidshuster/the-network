from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from context_helpers import make_test_context

from bot.core.templates import clear_template_cache, render_text
from bot.features.channels.stickies.subscription import _post_network_member_welcome
from bot.features.recipes.hub.relay.formatter import build_system_announcement_payload
from bot.features.recipes.hub.relay.service import RelayService


@pytest.mark.asyncio
async def test_network_welcome_claim_is_exclusive(db) -> None:
    context = make_test_context(db)
    network = await context.store.networks.create(
        guild_id=100, key="stingers", display_name="Stingers"
    )
    client = await context.store.clients.create(
        guild_id=100,
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
        subscribe_channel_id=501,
    )
    assert subscription.network_welcome_complete is False

    first, second = await asyncio.gather(
        context.store.clients.claim_network_welcome(subscription.id),
        context.store.clients.claim_network_welcome(subscription.id),
    )
    winners = [item for item in (first, second) if item is not None]
    assert len(winners) == 1
    assert winners[0].network_welcome_message_id == 0


@pytest.mark.asyncio
async def test_migration_baselines_existing_subscriptions_without_welcome_spam(db) -> None:
    """Fresh subscriptions after schema remain eligible; baseline is migration-time only."""
    context = make_test_context(db)
    network = await context.store.networks.create(
        guild_id=100, key="stingers", display_name="Stingers"
    )
    client = await context.store.clients.create(
        guild_id=100,
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
        subscribe_channel_id=501,
    )
    assert subscription.network_welcome_complete is False


@pytest.mark.asyncio
async def test_deliver_system_announcement_skips_joiner_and_blacklist(db) -> None:
    context = make_test_context(db)
    await context.refresh_projections()
    network = await context.store.networks.create(
        guild_id=100, key="stingers", display_name="Stingers"
    )
    joiner = await context.store.clients.create(
        guild_id=100,
        server_name="joiner",
        display_name="Joiner",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    incumbent = await context.store.clients.create(
        guild_id=100,
        server_name="incumbent",
        display_name="Incumbent",
        category_id=20,
        client_role_id=21,
        profile_channel_id=31,
        profile_message_id=41,
    )
    await context.store.clients.create_subscription(
        client_id=joiner.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=201,
        subscribe_channel_id=501,
    )
    incumbent_sub = await context.store.clients.create_subscription(
        client_id=incumbent.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=301,
        subscribe_channel_id=601,
    )
    await context.store.clients.add_blacklist(incumbent_sub.id, joiner.id)
    await context.refresh_projections()

    guild = MagicMock(spec=discord.Guild)
    joiner_channel = MagicMock(spec=discord.TextChannel)
    joiner_channel.send = AsyncMock()
    incumbent_channel = MagicMock(spec=discord.TextChannel)
    incumbent_channel.send = AsyncMock()
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {
            501: joiner_channel,
            601: incumbent_channel,
        }.get(channel_id)
    )
    message = MagicMock(spec=discord.Message)
    message.id = 9
    message.guild = guild
    message.attachments = []
    message.embeds = []
    message.author.display_avatar.url = "https://cdn.example/bot.png"

    service = RelayService(
        settings=context.settings,
        routing_service=context.routing_service,
        client_cache=context.client_cache,
        client_repo=context.store.clients,
        relay_record_repo=context.store.relay,
    )
    result = await service.deliver_system_announcement(
        message,
        network_id=network.id,
        body="welcome",
        about_client_id=joiner.id,
        exclude_client_id=joiner.id,
        author_icon_url="https://cdn.example/bot.png",
    )

    assert result.success
    joiner_channel.send.assert_not_called()
    incumbent_channel.send.assert_not_called()  # blacklisted

    await context.store.clients.remove_blacklist(incumbent_sub.id, joiner.id)
    result = await service.deliver_system_announcement(
        message,
        network_id=network.id,
        body="welcome",
        about_client_id=joiner.id,
        exclude_client_id=joiner.id,
        author_icon_url="https://cdn.example/bot.png",
    )
    assert result.success
    joiner_channel.send.assert_not_called()
    incumbent_channel.send.assert_awaited_once()
    embed = incumbent_channel.send.await_args.kwargs["embed"]
    assert embed.author.name == "The Network"
    assert embed.author.icon_url == "https://cdn.example/bot.png"
    assert embed.description == "welcome"


def test_network_member_connected_template_is_plain_text() -> None:
    clear_template_cache()
    text = render_text(
        "network_member_connected",
        network_key="stingers",
        network_display_name="Stingers",
        client_server_name="acme",
    )
    assert text.lstrip().startswith("[stingers]")
    assert "acme" in text


@pytest.mark.asyncio
async def test_failed_network_welcome_dispatch_leaves_retryable_source(
    monkeypatch: pytest.MonkeyPatch,
    db,
) -> None:
    context = make_test_context(db)
    network = await context.store.networks.create(
        guild_id=100, key="stingers", display_name="Stingers"
    )
    client = await context.store.clients.create(
        guild_id=100,
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
        subscribe_channel_id=501,
    )
    channel = MagicMock(spec=discord.TextChannel)
    posted = MagicMock(spec=discord.Message, id=9001)
    channel.send = AsyncMock(return_value=posted)
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
        AsyncMock(return_value=MagicMock(success=False, errors=("boom",))),
    )
    bot = MagicMock()
    bot.user.display_avatar.url = "https://cdn.example/bot.png"

    result = await _post_network_member_welcome(
        bot,
        context,
        MagicMock(spec=discord.Guild),
        client=client,
        network=network,
        subscription=subscription,
    )
    assert result.network_welcome_message_id == 9001
    assert result.network_welcome_complete is False
    channel.send.assert_awaited_once()

    channel.send.reset_mock()
    channel.fetch_message = AsyncMock(return_value=posted)
    monkeypatch.setattr(
        "bot.features.recipes.hub.announcements.dispatch_system_announcement",
        AsyncMock(return_value=MagicMock(success=True, errors=())),
    )
    result = await _post_network_member_welcome(
        bot,
        context,
        MagicMock(spec=discord.Guild),
        client=client,
        network=network,
        subscription=result,
    )
    channel.send.assert_not_called()
    assert result.network_welcome_complete is True


@pytest.mark.asyncio
async def test_client_relay_payload_still_uses_client_author() -> None:
    from bot.core.models.client import Client
    from bot.features.recipes.hub.relay.formatter import build_relay_embed_from_client

    client = Client(
        id=1,
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        timecode_enabled=False,
        emoji_id=55,
        emoji_name="acme",
        image_hash=None,
        degraded_reason=None,
    )
    message = MagicMock(spec=discord.Message)
    message.content = "hello"
    message.embeds = []
    message.attachments = []
    parts = build_relay_embed_from_client(message, client)
    assert parts.embed.author.name == "Acme"
    assert parts.embed.author.icon_url and "55" in parts.embed.author.icon_url


@pytest.mark.asyncio
async def test_build_system_payload_ignores_source_embeds() -> None:
    message = MagicMock(spec=discord.Message)
    message.attachments = []
    message.embeds = [MagicMock(title="should not appear", description="nope")]
    message.author.display_avatar.url = "https://cdn.example/bot.png"
    payload = await build_system_announcement_payload(
        message,
        body="plain body only",
        author_icon_url="https://cdn.example/bot.png",
    )
    assert payload.embed.description == "plain body only"
    assert payload.embed.title is None
