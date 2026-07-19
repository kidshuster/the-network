from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from bot.domain.profile import ServerProfile
from bot.services.profile_post import (
    PROFILE_CARD_FOOTER_PREFIX,
    build_profile_embed,
    profile_card_footer,
    profile_embed_content_signature,
)

logger = logging.getLogger(__name__)

_PROFILE_FOOTER_PREFIX = PROFILE_CARD_FOOTER_PREFIX
_bump_locks: dict[int, asyncio.Lock] = {}


@dataclass
class ProfileStickySyncSummary:
    checked: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


def is_profile_starter_message(message: discord.Message) -> bool:
    if not message.embeds or message.author.bot is False:
        return False
    footer = message.embeds[0].footer.text if message.embeds[0].footer else ""
    return footer.startswith(_PROFILE_FOOTER_PREFIX)


def _channel_lock(channel_id: int) -> asyncio.Lock:
    lock = _bump_locks.get(channel_id)
    if lock is None:
        lock = asyncio.Lock()
        _bump_locks[channel_id] = lock
    return lock


async def _resolve_profile_starter_message(
    channel: discord.TextChannel,
    profile: ServerProfile,
) -> discord.Message | None:
    try:
        starter = await channel.fetch_message(profile.profile_starter_message_id)
        if is_profile_starter_message(starter):
            return starter
    except discord.HTTPException:
        pass

    async for message in channel.history(limit=50):
        if is_profile_starter_message(message):
            return message
    return None


async def refresh_profile_starter_embed(
    message: discord.Message,
    profile: ServerProfile,
    *,
    network_key: str | None,
    view: discord.ui.View | None = None,
) -> None:
    embed = build_profile_embed(
        server_name=profile.server_name,
        display_name=profile.display_name,
        source_channel_id=profile.source_channel_id,
        network_key=network_key,
        enabled=profile.enabled,
        emoji_id=profile.emoji_id,
    )
    kwargs: dict = {"embed": embed}
    if view is not None:
        kwargs["view"] = view
    await message.edit(**kwargs)


async def sync_profile_sticky(
    channel: discord.TextChannel,
    profile: ServerProfile,
    *,
    network_key: str | None,
    edit_view_factory: Callable[[int], discord.ui.View],
    update_starter_message_id: Callable[[int, int], Awaitable[None]],
) -> str:
    """Refresh a profile card when its embed template changed. Returns updated/skipped/failed."""
    desired_embed = build_profile_embed(
        server_name=profile.server_name,
        display_name=profile.display_name,
        source_channel_id=profile.source_channel_id,
        network_key=network_key,
        enabled=profile.enabled,
        emoji_id=profile.emoji_id,
    )
    desired_signature = profile_embed_content_signature(desired_embed)
    view = edit_view_factory(profile.profile_thread_id)

    starter = await _resolve_profile_starter_message(channel, profile)
    if starter is None:
        return "failed"

    if starter.embeds:
        existing_embed = starter.embeds[0]
        existing_signature = profile_embed_content_signature(existing_embed)
        footer = existing_embed.footer.text if existing_embed.footer else ""
        if footer == profile_card_footer() and existing_signature == desired_signature:
            try:
                await starter.edit(view=view)
            except discord.HTTPException:
                pass
            if starter.id != profile.profile_starter_message_id:
                await update_starter_message_id(profile.profile_thread_id, starter.id)
            return "skipped"

    new_message = await repost_profile_sticky_after_edit(
        channel,
        profile,
        display_name=profile.display_name,
        enabled=profile.enabled,
        network_key=network_key,
        edit_view_factory=edit_view_factory,
        existing_message=starter,
    )
    if new_message is None:
        return "failed"

    await update_starter_message_id(profile.profile_thread_id, new_message.id)
    return "updated"


async def sync_all_profile_stickies(
    guild: discord.Guild,
    profiles: list[ServerProfile],
    *,
    resolve_network_key: Callable[[int], Awaitable[str | None]],
    update_starter_message_id: Callable[[int, int], Awaitable[None]],
    edit_view_factory: Callable[[int], discord.ui.View],
) -> ProfileStickySyncSummary:
    summary = ProfileStickySyncSummary()
    for profile in profiles:
        if profile.guild_id != guild.id:
            continue
        summary.checked += 1
        channel = guild.get_channel(profile.source_channel_id)
        if not isinstance(channel, discord.TextChannel):
            summary.failed += 1
            continue

        network_key = await resolve_network_key(profile.network_id)
        async with _channel_lock(channel.id):
            result = await sync_profile_sticky(
                channel,
                profile,
                network_key=network_key,
                edit_view_factory=edit_view_factory,
                update_starter_message_id=update_starter_message_id,
            )
        if result == "updated":
            summary.updated += 1
        elif result == "skipped":
            summary.skipped += 1
        else:
            summary.failed += 1
    return summary


async def bump_profile_sticky(
    channel: discord.TextChannel,
    profile: ServerProfile,
    *,
    bot_user: discord.ClientUser,
    edit_view_factory: Callable[[int], discord.ui.View],
) -> discord.Message | None:
    try:
        starter = await channel.fetch_message(profile.profile_starter_message_id)
    except discord.HTTPException:
        return None

    if not starter.embeds:
        return None

    embed = starter.embeds[0]
    view = edit_view_factory(profile.profile_thread_id)

    try:
        await starter.delete()
    except discord.HTTPException:
        return None

    try:
        return await channel.send(embed=embed, view=view)
    except discord.HTTPException:
        logger.warning(
            "Could not repost profile sticky",
            extra={"channel_id": channel.id, "profile_id": profile.id},
        )
        return None


async def maybe_bump_profile_sticky(
    message: discord.Message,
    *,
    get_profile_by_source_channel: Callable[[int], Awaitable[ServerProfile | None]],
    update_starter_message_id: Callable[[int, int], Awaitable[None]],
    bot_user: discord.ClientUser,
    edit_view_factory: Callable[[int], discord.ui.View],
) -> None:
    if message.guild is None or not isinstance(message.channel, discord.TextChannel):
        return
    if message.author.id == bot_user.id:
        return

    profile = await get_profile_by_source_channel(message.channel.id)
    if profile is None:
        return
    if message.id == profile.profile_starter_message_id:
        return
    if is_profile_starter_message(message):
        return

    lock = _channel_lock(message.channel.id)
    if lock.locked():
        return

    async with lock:
        await asyncio.sleep(0.75)
        profile = await get_profile_by_source_channel(message.channel.id)
        if profile is None:
            return

        new_message = await bump_profile_sticky(
            message.channel,
            profile,
            bot_user=bot_user,
            edit_view_factory=edit_view_factory,
        )
        if new_message is None:
            return

        await update_starter_message_id(profile.profile_thread_id, new_message.id)
        logger.debug(
            "Bumped profile sticky to channel bottom",
            extra={
                "channel_id": message.channel.id,
                "profile_id": profile.id,
                "message_id": new_message.id,
            },
        )


async def repost_profile_sticky_after_edit(
    channel: discord.TextChannel,
    profile: ServerProfile,
    *,
    display_name: str,
    enabled: bool,
    network_key: str | None,
    edit_view_factory: Callable[[int], discord.ui.View],
    existing_message: discord.Message | None = None,
    emoji_id: int | None = None,
) -> discord.Message | None:
    old = existing_message
    if old is None:
        try:
            old = await channel.fetch_message(profile.profile_starter_message_id)
        except discord.HTTPException:
            old = None
    if old is not None:
        try:
            await old.delete()
        except discord.HTTPException:
            pass

    resolved_emoji_id = profile.emoji_id if emoji_id is None else emoji_id
    embed = build_profile_embed(
        server_name=profile.server_name,
        display_name=display_name,
        source_channel_id=profile.source_channel_id,
        network_key=network_key,
        enabled=enabled,
        emoji_id=resolved_emoji_id,
    )
    view = edit_view_factory(profile.profile_thread_id)
    try:
        return await channel.send(embed=embed, view=view)
    except discord.HTTPException:
        return None
