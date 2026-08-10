from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.join_requests_sticky import (
    build_how_to_join_embed,
    build_how_to_join_footer,
    format_how_to_join_sticky_location,
    parse_how_to_join_sticky_location,
    sync_hub_join_sticky,
)


@pytest.mark.asyncio
async def test_sync_hub_join_sticky_wipes_before_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wipe = AsyncMock(return_value=(2, None))
    monkeypatch.setattr(
        "bot.services.discord_cleanup.wipe_text_channel",
        wipe,
    )

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 20
    channel.permissions_for.return_value = MagicMock(
        view_channel=True,
        send_messages=True,
        embed_links=True,
    )
    message = MagicMock(spec=discord.Message)
    message.id = 88
    channel.send = AsyncMock(return_value=message)

    bot_member = MagicMock(spec=discord.Member)
    bot_member.id = 1
    get_setting = AsyncMock(return_value=None)
    set_setting = AsyncMock()
    view = MagicMock(spec=discord.ui.View)

    result = await sync_hub_join_sticky(
        MagicMock(spec=discord.Guild),
        bot_member,
        channel,
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


def test_build_how_to_join_embed_is_minimal_prejoin_cta() -> None:
    embed = build_how_to_join_embed()
    body = (embed.description or "") + " ".join(field.value or "" for field in embed.fields)
    assert "Join Network" in body
    assert "network-profile" in body
    assert "Enable Community" not in body
    assert "Blacklist" not in body
    assert embed.footer is not None
    assert embed.footer.text == build_how_to_join_footer()


def test_parse_how_to_join_sticky_location_supports_channel_message_pair() -> None:
    location = parse_how_to_join_sticky_location("123:456")
    assert location is not None
    assert location.channel_id == 123
    assert location.message_id == 456


def test_parse_how_to_join_sticky_location_supports_legacy_message_only() -> None:
    location = parse_how_to_join_sticky_location("456", fallback_channel_id=123)
    assert location is not None
    assert location.channel_id == 123
    assert location.message_id == 456


def test_format_how_to_join_sticky_location() -> None:
    assert format_how_to_join_sticky_location(123, 456) == "123:456"
