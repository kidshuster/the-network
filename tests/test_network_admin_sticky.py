from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.stickies.network_admin_sticky import sync_network_admin_sticky


@pytest.mark.asyncio
async def test_sync_network_admin_sticky_wipes_before_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wipe = AsyncMock(return_value=(3, None))
    monkeypatch.setattr(
        "bot.discord_util.cleanup.wipe_text_channel",
        wipe,
    )

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 10
    channel.permissions_for.return_value = MagicMock(
        view_channel=True,
        send_messages=True,
        embed_links=True,
    )
    message = MagicMock(spec=discord.Message)
    message.id = 99
    channel.send = AsyncMock(return_value=message)

    bot_member = MagicMock(spec=discord.Member)
    bot_member.id = 1
    context = MagicMock()
    context.store.networks.list_all = AsyncMock(return_value=[])
    context.store.clients.list_subscriptions_by_network = AsyncMock(return_value=[])
    get_setting = AsyncMock(return_value=None)
    set_setting = AsyncMock()
    view = MagicMock(spec=discord.ui.View)

    result = await sync_network_admin_sticky(
        MagicMock(spec=discord.Guild),
        bot_member,
        channel,
        context,
        view,
        get_setting=get_setting,
        set_setting=set_setting,
        wipe_channel=True,
    )

    wipe.assert_awaited_once_with(channel, bot_member)
    channel.send.assert_awaited_once()
    set_setting.assert_awaited_once()
    assert result.success is True
    assert result.message is message
