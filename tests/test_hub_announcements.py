from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.config import Settings
from bot.domain.client import Client
from bot.services.hub_announcements import (
    can_post_hub_announcement,
    is_hub_announcements_client,
    parse_announcement_content,
)


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    return Settings(_env_file=None)


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
        timecode_enabled=True,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


def test_is_hub_announcements_client_matches_configured_server_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch)
    assert is_hub_announcements_client(
        _client(settings.hub_announcements_server_name),
        settings,
    )
    assert not is_hub_announcements_client(_client("acme"), settings)


def test_parse_announcement_content_defaults_to_all_networks() -> None:
    parsed = parse_announcement_content(
        "Maintenance tonight.",
        available_keys={"smoke", "stingers"},
    )
    assert parsed.error is None
    assert parsed.network_keys == ("smoke", "stingers")
    assert parsed.body == "Maintenance tonight."


def test_parse_announcement_content_single_network_prefix() -> None:
    parsed = parse_announcement_content(
        "[stingers]\nMaintenance tonight.",
        available_keys={"smoke", "stingers"},
    )
    assert parsed.error is None
    assert parsed.network_keys == ("stingers",)
    assert parsed.body == "Maintenance tonight."


def test_parse_announcement_content_unknown_network() -> None:
    parsed = parse_announcement_content(
        "[missing]\nHello",
        available_keys={"smoke"},
    )
    assert parsed.error is not None
    assert "Unknown network" in parsed.error


def test_parse_announcement_content_requires_body_after_prefix() -> None:
    parsed = parse_announcement_content(
        "[smoke]",
        available_keys={"smoke"},
    )
    assert parsed.error is not None


def test_can_post_hub_announcement_allows_operator_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch)
    guild = MagicMock(spec=discord.Guild)
    operator = MagicMock(spec=discord.Role)
    operator.name = settings.network_operator_role_name
    guild.roles = [operator]

    member = MagicMock(spec=discord.Member)
    member.roles = [operator]
    member.guild_permissions.manage_guild = False

    assert can_post_hub_announcement(member, guild, settings)


@pytest.mark.asyncio
async def test_relay_skips_hub_announcements_subscribe_destination(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bot.db.repositories import ClientRepository, NetworkRepository, RelayRecordRepository
    from bot.services.client_cache import ClientCache
    from bot.services.relay_service import RelayService
    from bot.services.routing_service import RoutingService

    settings = _settings(monkeypatch)
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    network = await network_repo.create(guild_id=100, key="smoke", display_name="Smoke")

    publisher = await client_repo.create(
        guild_id=100,
        server_name="publisher",
        display_name="Publisher",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
    )
    await client_repo.update_emoji_fields(
        publisher.id,
        emoji_id=888,
        emoji_name="net_publisher",
        image_hash="hash",
        degraded_reason=None,
    )
    hub = await client_repo.create(
        guild_id=100,
        server_name=settings.hub_announcements_server_name,
        display_name=settings.hub_announcements_display_name,
        category_id=12,
        client_role_id=22,
        profile_channel_id=32,
        profile_message_id=42,
    )
    subscriber = await client_repo.create(
        guild_id=100,
        server_name="subscriber",
        display_name="Subscriber",
        category_id=11,
        client_role_id=21,
        profile_channel_id=31,
        profile_message_id=41,
    )

    await client_repo.create_subscription(
        client_id=publisher.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=1001,
        subscribe_channel_id=1002,
    )
    await client_repo.create_subscription(
        client_id=hub.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=2001,
        subscribe_channel_id=2002,
    )
    await client_repo.create_subscription(
        client_id=subscriber.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=3001,
        subscribe_channel_id=3002,
    )

    client_cache = ClientCache(client_repo)
    await client_cache.load_cache()
    routing = RoutingService(network_repo, client_repo)
    routing.attach_client_cache(client_cache)
    await routing.load_cache()
    relay_records = RelayRecordRepository(db)
    relay_service = RelayService(
        settings,
        routing,
        client_cache,
        client_repo,
        relay_records,
    )

    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    publish_channel = MagicMock(spec=discord.TextChannel)
    publish_channel.id = 1001
    hub_subscribe = MagicMock(spec=discord.TextChannel)
    hub_subscribe.id = 2002
    hub_subscribe.send = AsyncMock()
    subscriber_subscribe = MagicMock(spec=discord.TextChannel)
    subscriber_subscribe.id = 3002
    sent_message = MagicMock(spec=discord.Message)
    sent_message.id = 9001
    sent_message.publish = AsyncMock()
    subscriber_subscribe.send = AsyncMock(return_value=sent_message)

    guild.get_channel = MagicMock(
        side_effect=lambda cid: {
            1001: publish_channel,
            2002: hub_subscribe,
            3002: subscriber_subscribe,
        }.get(cid),
    )

    message = MagicMock(spec=discord.Message)
    message.id = 5001
    message.guild = guild
    message.channel = publish_channel
    message.webhook_id = 777
    message.author = MagicMock(bot=True)
    message.content = "Hello network"
    message.embeds = []
    message.attachments = []

    result = await relay_service.relay_message(message)
    assert result is not None
    assert result.success
    subscriber_subscribe.send.assert_awaited_once()
    hub_subscribe.send.assert_not_called()
