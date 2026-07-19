from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.domain.profile import ServerProfile
from bot.services.profile_post import build_profile_embed, profile_card_footer
from bot.services.profile_sticky import sync_profile_sticky


def _profile(**overrides: object) -> ServerProfile:
    base = {
        "id": 1,
        "guild_id": 100,
        "profile_thread_id": 501,
        "profile_starter_message_id": 900,
        "source_channel_id": 700,
        "network_id": 2,
        "server_name": "Alpha",
        "display_name": "Alpha Ops",
        "enabled": True,
        "emoji_id": None,
        "emoji_name": None,
        "image_hash": None,
        "degraded_reason": None,
        "partner_role_id": None,
        "profile_forum_channel_id": None,
    }
    base.update(overrides)
    return ServerProfile(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_sync_profile_sticky_skips_current_card(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _profile()
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = profile.source_channel_id

    desired = build_profile_embed(
        server_name=profile.server_name,
        display_name=profile.display_name,
        source_channel_id=profile.source_channel_id,
        network_key="stingers",
        enabled=True,
        emoji_id=profile.emoji_id,
    )
    starter = MagicMock(spec=discord.Message)
    starter.id = profile.profile_starter_message_id
    starter.embeds = [desired]
    starter.attachments = []
    starter.author.bot = True
    starter.edit = AsyncMock()

    monkeypatch.setattr(
        "bot.services.profile_sticky._resolve_profile_starter_message",
        AsyncMock(return_value=starter),
    )

    update_starter = AsyncMock()
    result = await sync_profile_sticky(
        channel,
        profile,
        network_key="stingers",
        edit_view_factory=lambda _thread_id: MagicMock(spec=discord.ui.View),
        update_starter_message_id=update_starter,
    )

    assert result == "skipped"
    starter.edit.assert_awaited_once()
    update_starter.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_profile_sticky_updates_outdated_card(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _profile()
    channel = MagicMock(spec=discord.TextChannel)

    outdated = build_profile_embed(
        server_name=profile.server_name,
        display_name=profile.display_name,
        source_channel_id=profile.source_channel_id,
        network_key="stingers",
        enabled=True,
    )
    outdated.set_footer(text="The Network • profile card • legacy footer")

    starter = MagicMock(spec=discord.Message)
    starter.id = profile.profile_starter_message_id
    starter.embeds = [outdated]
    starter.attachments = []

    new_message = MagicMock(spec=discord.Message)
    new_message.id = 901
    repost = AsyncMock(return_value=new_message)
    monkeypatch.setattr(
        "bot.services.profile_sticky._resolve_profile_starter_message",
        AsyncMock(return_value=starter),
    )
    monkeypatch.setattr("bot.services.profile_sticky.repost_profile_sticky_after_edit", repost)

    update_starter = AsyncMock()
    result = await sync_profile_sticky(
        channel,
        profile,
        network_key="stingers",
        edit_view_factory=lambda _thread_id: MagicMock(spec=discord.ui.View),
        update_starter_message_id=update_starter,
    )

    assert result == "updated"
    repost.assert_awaited_once()
    update_starter.assert_awaited_once_with(profile.profile_thread_id, 901)


def test_profile_card_footer_includes_version() -> None:
    assert "v3" in profile_card_footer()
