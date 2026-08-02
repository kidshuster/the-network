from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.guild_permissions import build_leaders_channel_overwrites
from bot.services.subscription_setup import (
    SubscriptionSetupState,
    derive_network_link_status,
    is_publish_configured,
)


@pytest.mark.asyncio
async def test_is_publish_configured_true_when_channel_follower_webhook() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    follower = MagicMock()
    follower.is_channel_follower.return_value = True
    channel.webhooks = AsyncMock(return_value=[follower])

    assert await is_publish_configured(channel) is True


@pytest.mark.asyncio
async def test_is_publish_configured_false_without_follower_webhooks() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    incoming = MagicMock()
    incoming.is_channel_follower.return_value = False
    channel.webhooks = AsyncMock(return_value=[incoming])

    assert await is_publish_configured(channel) is False


def test_derive_network_link_status() -> None:
    assert derive_network_link_status(
        network_active=False,
        publish_configured=True,
        subscribe_confirmed=True,
    ) == "Disabled"
    assert derive_network_link_status(
        network_active=True,
        publish_configured=False,
        subscribe_confirmed=True,
    ) == "Not Configured"
    assert derive_network_link_status(
        network_active=True,
        publish_configured=True,
        subscribe_confirmed=False,
    ) == "Not Configured"
    assert derive_network_link_status(
        network_active=True,
        publish_configured=True,
        subscribe_confirmed=True,
    ) == "Active"


def test_subscription_setup_state_fully_configured() -> None:
    state = SubscriptionSetupState(
        publish_configured=True,
        subscribe_confirmed=True,
        network_active=True,
    )
    assert state.fully_configured is True
    assert state.link_status == "Active"
