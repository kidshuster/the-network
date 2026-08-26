from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.discord.step_runner import run_guild_step
from bot.features.recipes.hub.clients.subscription import resolve_subscription_channels_in_category


@dataclass
class _StepResult:
    failed_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@pytest.mark.asyncio
async def test_run_guild_step_records_http_exception() -> None:
    result = _StepResult()

    async def _fail() -> None:
        raise discord.HTTPException(MagicMock(), "Missing Permissions")

    value = await run_guild_step(result, "delete channel", _fail)

    assert value is None
    assert result.failed_steps
    assert "Missing Permissions" in result.failed_steps[0]


def test_resolve_subscription_channels_falls_back_to_category_names() -> None:
    from bot.core.models.client_subscription import ClientSubscription

    category = MagicMock(spec=discord.CategoryChannel)
    publish = MagicMock(spec=discord.TextChannel)
    publish.id = 501
    publish.name = "acme-stingers-publish"
    subscribe = MagicMock(spec=discord.VoiceChannel)
    subscribe.id = 502
    subscribe.name = "acme-stingers-subscribe"
    category.channels = [publish, subscribe]

    guild = MagicMock(spec=discord.Guild)
    guild.get_channel = MagicMock(return_value=None)

    client = MagicMock()
    client.server_name = "Acme"
    subscription = ClientSubscription(
        id=1,
        client_id=1,
        network_id=2,
        network_key="stingers",
        publish_channel_id=999,
        subscribe_channel_id=998,
        announcements_channel_id=None,
        moderation_message_id=None,
        publish_setup_message_id=None,
        subscribe_setup_message_id=None,
        announcements_sticky_message_id=None,
        activation_welcome_message_id=None,
        network_welcome_message_id=None,
        network_welcome_complete=False,
        subscribe_confirmed=False,
        enabled=True,
    )

    resolved_publish, resolved_subscribe = resolve_subscription_channels_in_category(
        guild,
        category,
        subscription,
        "stingers",
        client=client,
    )

    assert resolved_publish is publish
    assert resolved_subscribe is subscribe


@pytest.mark.asyncio
async def test_sync_stored_embed_sticky_skips_when_current() -> None:
    from bot.features.channels.stickies.reconciler import sync_stored_embed_sticky

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 10
    channel.permissions_for.return_value = MagicMock(
        view_channel=True,
        send_messages=True,
        embed_links=True,
    )
    existing = MagicMock(spec=discord.Message)
    existing.id = 55
    existing.author = MagicMock(id=1)
    embed = discord.Embed(title="Sticky", description="Body")
    existing.embeds = [embed]
    existing.edit = AsyncMock()
    channel.fetch_message = AsyncMock(return_value=existing)
    channel.send = AsyncMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_member.id = 1
    view = MagicMock(spec=discord.ui.View)
    get_setting = AsyncMock(return_value="10:55")
    set_setting = AsyncMock()

    result = await sync_stored_embed_sticky(
        channel,
        bot_member,
        get_setting=get_setting,
        set_setting=set_setting,
        settings_key="test_sticky",
        desired_embed=embed,
        view=view,
        is_current=lambda _existing: True,
        refresh_current=AsyncMock(),
    )

    assert result.success is True
    assert result.skipped is True
    channel.send.assert_not_called()
    set_setting.assert_awaited_once_with("test_sticky", "10:55")
