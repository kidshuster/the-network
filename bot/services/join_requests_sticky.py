from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from bot.services.sticky_sync import (
    embed_content_signature,
    sync_stored_embed_sticky,
)

logger = logging.getLogger(__name__)

HOW_TO_JOIN_VERSION = 10
HOW_TO_JOIN_SETTINGS_KEY = "hub_join_the_network_sticky"
HOW_TO_JOIN_FOOTER_PREFIX = "The Network • join the network"


@dataclass(frozen=True)
class HowToJoinStickyResult:
    success: bool
    message: discord.Message | None = None
    updated: bool = False
    skipped: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class HowToJoinStickyLocation:
    channel_id: int
    message_id: int


def format_how_to_join_sticky_location(channel_id: int, message_id: int) -> str:
    return f"{channel_id}:{message_id}"


def parse_how_to_join_sticky_location(
    raw: str | None,
    *,
    fallback_channel_id: int | None = None,
) -> HowToJoinStickyLocation | None:
    if raw is None:
        return None
    if ":" in raw:
        channel_part, message_part = raw.split(":", 1)
        return HowToJoinStickyLocation(int(channel_part), int(message_part))
    if fallback_channel_id is not None:
        return HowToJoinStickyLocation(fallback_channel_id, int(raw))
    return None


def build_how_to_join_footer() -> str:
    return f"{HOW_TO_JOIN_FOOTER_PREFIX} • v{HOW_TO_JOIN_VERSION}"


def build_how_to_join_embed() -> discord.Embed:
    from bot.messages import render_embed

    return render_embed("join_the_network", version=HOW_TO_JOIN_VERSION)


async def sync_hub_join_sticky(
    guild: discord.Guild,
    bot_member: discord.Member,
    channel: discord.TextChannel,
    view: discord.ui.View,
    *,
    get_setting: Callable[[str], Awaitable[str | None]],
    set_setting: Callable[[str, str], Awaitable[None]],
    wipe_channel: bool = False,
) -> HowToJoinStickyResult:
    desired_embed = build_how_to_join_embed()
    desired_signature = embed_content_signature(desired_embed)

    async def refresh_current(
        message: discord.Message,
        _embed: discord.Embed,
        sticky_view: discord.ui.View,
    ) -> None:
        await message.edit(view=sticky_view)

    def is_current(existing_embed: discord.Embed) -> bool:
        footer = existing_embed.footer.text if existing_embed.footer else ""
        return (
            footer == build_how_to_join_footer()
            and embed_content_signature(existing_embed) == desired_signature
        )

    result = await sync_stored_embed_sticky(
        channel,
        bot_member,
        get_setting=get_setting,
        set_setting=set_setting,
        settings_key=HOW_TO_JOIN_SETTINGS_KEY,
        desired_embed=desired_embed,
        view=view,
        is_current=is_current,
        refresh_current=refresh_current,
        wipe_channel=wipe_channel,
    )
    return HowToJoinStickyResult(
        success=result.success,
        message=result.message,
        updated=result.updated,
        skipped=result.skipped,
        reason=result.reason,
    )
