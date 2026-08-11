from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from bot.features.channels.stickies.loader import sticky_spec
from bot.features.channels.stickies.reconciler import (
    StoredStickyDefinition,
    embed_content_signature,
    sync_stored_sticky,
)

logger = logging.getLogger(__name__)

_SPEC = sticky_spec("join-the-network")
HOW_TO_JOIN_VERSION = _SPEC.version
HOW_TO_JOIN_SETTINGS_KEY = _SPEC.settings_key or ""
HOW_TO_JOIN_FOOTER_PREFIX = _SPEC.footer_marker


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
    from bot.app.templates import render_embed

    return render_embed(_SPEC.template, version=HOW_TO_JOIN_VERSION)


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

    definition = StoredStickyDefinition(
        settings_key=HOW_TO_JOIN_SETTINGS_KEY,
        build_embed=build_how_to_join_embed,
        is_current=lambda existing_embed: (
            (existing_embed.footer.text if existing_embed.footer else "")
            == build_how_to_join_footer()
            and embed_content_signature(existing_embed) == desired_signature
        ),
        refresh_current=refresh_current,
    )
    result = await sync_stored_sticky(
        channel,
        bot_member,
        view,
        get_setting=get_setting,
        set_setting=set_setting,
        definition=definition,
        wipe_channel=wipe_channel,
    )
    return HowToJoinStickyResult(
        success=result.success,
        message=result.message,
        updated=result.updated,
        skipped=result.skipped,
        reason=result.reason,
    )
