from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.features.recipes.hub.clients import publish_follow_guard as guard


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
        read_only=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


def _subscription() -> ClientSubscription:
    return ClientSubscription(
        id=5,
        client_id=1,
        network_id=2,
        network_key="stingers",
        publish_channel_id=201,
        subscribe_channel_id=501,
        announcements_channel_id=None,
        moderation_message_id=None,
        publish_setup_message_id=None,
        subscribe_setup_message_id=None,
        announcements_sticky_message_id=None,
        activation_welcome_message_id=None,
        network_welcome_message_id=None,
        network_welcome_complete=False,
        subscribe_confirmed=True,
        enabled=True,
    )


@pytest.mark.asyncio
async def test_remediate_deletes_hub_sourced_follow_and_notifies_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100

    publish = MagicMock(spec=discord.TextChannel)
    publish.id = 201
    publish.mention = "#publish"
    publish.guild = guild

    hub_follow = MagicMock()
    hub_follow.type = discord.WebhookType.channel_follower
    hub_follow.id = 9
    hub_follow.source_guild = MagicMock(id=100)
    hub_follow.source_channel = MagicMock(id=501)
    hub_follow.delete = AsyncMock()

    external = MagicMock()
    external.type = discord.WebhookType.channel_follower
    external.id = 10
    external.source_guild = MagicMock(id=999)
    external.source_channel = MagicMock(id=1)
    external.delete = AsyncMock()

    publish.webhooks = AsyncMock(return_value=[hub_follow, external])

    profile = MagicMock(spec=discord.TextChannel)
    profile.send = AsyncMock()

    monkeypatch.setattr(guard, "fetch_publish_channel", AsyncMock(return_value=publish))
    monkeypatch.setattr(
        guard,
        "resolve_client_profile_channel",
        AsyncMock(return_value=profile),
    )
    monkeypatch.setattr(
        guard,
        "render_embed",
        lambda *_args, **_kwargs: MagicMock(),
    )

    inspection = await guard.remediate_hub_sourced_publish_follows(
        guild,
        client=_client(),
        subscription=_subscription(),
        known_hub_channel_ids=frozenset({501}),
    )

    hub_follow.delete.assert_awaited_once()
    external.delete.assert_not_called()
    profile.send.assert_awaited_once()
    assert inspection is not None
    assert inspection.configured is True
