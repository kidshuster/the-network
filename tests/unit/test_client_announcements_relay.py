from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from subscription_helpers import make_client_subscription

from bot.core.models.client import Client
from bot.features.recipes.hub.relay.service import RelayService


def _client(*, read_only: bool = True) -> Client:
    return Client(
        id=1,
        guild_id=100,
        server_name="Acme",
        display_name="Acme",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        timecode_enabled=True,
        read_only=read_only,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


@pytest.mark.asyncio
async def test_relay_announcements_respects_blacklist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher_sub = make_client_subscription(
        id=1,
        client_id=1,
        network_id=2,
        announcements_channel_id=500,
        publish_channel_id=None,
    )
    dest_sub = make_client_subscription(
        id=2,
        client_id=3,
        network_id=2,
        subscribe_channel_id=600,
        publish_channel_id=None,
    )
    publisher = _client(read_only=True)
    destination = Client(
        id=3,
        guild_id=100,
        server_name="Other",
        display_name="Other",
        category_id=11,
        client_role_id=21,
        profile_channel_id=31,
        profile_message_id=41,
        enabled=True,
        timecode_enabled=True,
        read_only=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )

    routing = MagicMock()
    routing.resolve_announcements_subscription = MagicMock(return_value=publisher_sub)
    routing.get_by_id = MagicMock(
        return_value=MagicMock(id=2, key="stingers", enabled=True)
    )
    routing.list_network_subscriptions = MagicMock(return_value=[publisher_sub, dest_sub])

    clients = MagicMock()
    clients.get_client = MagicMock(side_effect=lambda cid: {1: publisher, 3: destination}.get(cid))

    client_repo = MagicMock()
    client_repo.is_relay_blocked = AsyncMock(return_value=True)

    relay_records = MagicMock()
    relay_records.exists = AsyncMock(return_value=False)
    relay_records.create_pending = AsyncMock(return_value=MagicMock(id=9))
    relay_records.update_status = AsyncMock()

    settings = MagicMock(guild_id=100)
    service = RelayService(settings, routing, clients, client_repo, relay_records)

    role = MagicMock(spec=discord.Role, id=20)
    author = MagicMock(spec=discord.Member)
    author.bot = False
    author.roles = [role]
    author.guild_permissions = MagicMock(manage_guild=False)

    guild = MagicMock(spec=discord.Guild, id=100)
    guild.get_role = MagicMock(return_value=role)
    guild.get_channel = MagicMock(return_value=MagicMock(spec=discord.TextChannel))

    channel = MagicMock(spec=discord.TextChannel, id=500)
    message = MagicMock(spec=discord.Message)
    message.id = 42
    message.guild = guild
    message.channel = channel
    message.author = author
    message.webhook_id = None
    message.content = "hello network"
    message.attachments = []
    message.embeds = []

    monkeypatch.setattr(
        "bot.features.recipes.hub.relay.formatter.build_relay_payload_from_client",
        AsyncMock(return_value=MagicMock(embed=MagicMock(), files=[])),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.relay.formatter.has_relayable_content",
        MagicMock(return_value=True),
    )

    result = await service.relay_announcements_message(message)
    assert result is not None
    assert result.success is False
    assert result.error == "no relay destinations"
    client_repo.is_relay_blocked.assert_awaited()
