from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.ui.join_views import JoinNetworkView

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

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


JoinStickyResult = HowToJoinStickyResult


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


def embed_content_signature(embed: discord.Embed) -> str:
    payload = {
        "title": embed.title,
        "description": embed.description,
        "fields": [(field.name, field.value, field.inline) for field in embed.fields],
        "footer": embed.footer.text if embed.footer else None,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_how_to_join_embed() -> discord.Embed:
    from bot.messages import render_embed

    return render_embed("join_the_network", version=HOW_TO_JOIN_VERSION)


async def post_how_to_join_message(
    channel: discord.TextChannel,
    bot: NetworkRelayBot,
) -> discord.Message:
    view = JoinNetworkView(bot)
    bot.add_view(view)
    return await channel.send(embed=build_how_to_join_embed(), view=view, silent=True)


async def sync_hub_join_sticky(
    guild: discord.Guild,
    bot_member: discord.Member,
    bot: NetworkRelayBot,
    channel: discord.TextChannel,
    *,
    get_setting: Callable[[str], Awaitable[str | None]],
    set_setting: Callable[[str, str], Awaitable[None]],
    wipe_channel: bool = False,
) -> HowToJoinStickyResult:
    permissions = channel.permissions_for(bot_member)
    if not permissions.view_channel or not permissions.send_messages or not permissions.embed_links:
        return HowToJoinStickyResult(
            success=False,
            skipped=True,
            reason=(
                f"The bot cannot post embeds in {channel.mention}. "
                "Grant View Channel, Send Messages, and Embed Links there."
            ),
        )

    if wipe_channel:
        from bot.services.discord_cleanup import wipe_text_channel

        _deleted, wipe_error = await wipe_text_channel(channel, bot_member)
        if wipe_error is not None:
            return HowToJoinStickyResult(success=False, reason=wipe_error)

    desired_embed = build_how_to_join_embed()
    desired_signature = embed_content_signature(desired_embed)
    view = JoinNetworkView(bot)
    bot.add_view(view)

    if wipe_channel:
        message = await channel.send(embed=desired_embed, view=view, silent=True)
        await set_setting(HOW_TO_JOIN_SETTINGS_KEY, f"{channel.id}:{message.id}")
        return HowToJoinStickyResult(success=True, message=message, updated=True)

    stored_raw = await get_setting(HOW_TO_JOIN_SETTINGS_KEY)
    existing: discord.Message | None = None
    if stored_raw:
        try:
            message_id = int(stored_raw.split(":")[-1])
            existing = await channel.fetch_message(message_id)
        except (ValueError, discord.HTTPException):
            existing = None

    if existing is not None and existing.author.id == bot_member.id and existing.embeds:
        existing_signature = embed_content_signature(existing.embeds[0])
        footer = existing.embeds[0].footer.text if existing.embeds[0].footer else ""
        if footer == build_how_to_join_footer() and existing_signature == desired_signature:
            await existing.edit(view=view)
            await set_setting(HOW_TO_JOIN_SETTINGS_KEY, f"{channel.id}:{existing.id}")
            return HowToJoinStickyResult(success=True, message=existing, skipped=True)
        try:
            await existing.edit(embed=desired_embed, view=view)
            await set_setting(HOW_TO_JOIN_SETTINGS_KEY, f"{channel.id}:{existing.id}")
            return HowToJoinStickyResult(success=True, message=existing, updated=True)
        except discord.HTTPException:
            try:
                await existing.delete()
            except discord.HTTPException:
                pass

    message = await channel.send(embed=desired_embed, view=view, silent=True)
    await set_setting(HOW_TO_JOIN_SETTINGS_KEY, f"{channel.id}:{message.id}")
    return HowToJoinStickyResult(success=True, message=message, updated=True)


# Legacy names for gradual migration
def how_to_join_sticky_settings_key(_key):
    return HOW_TO_JOIN_SETTINGS_KEY
sync_network_how_to_join_sticky = sync_hub_join_sticky
sync_network_join_sticky = sync_hub_join_sticky
build_join_requests_embed = build_how_to_join_embed
