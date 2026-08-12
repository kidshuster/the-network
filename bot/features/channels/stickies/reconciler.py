from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast

import discord

logger = logging.getLogger(__name__)

SETUP_STICKY_HISTORY_LIMIT = 50


def embed_content_signature(embed: discord.Embed) -> str:
    payload = {
        "title": embed.title,
        "description": embed.description,
        "fields": [(field.name, field.value, field.inline) for field in embed.fields],
        "footer": embed.footer.text if embed.footer else None,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sticky_channel_embed_permission_error(
    channel: discord.TextChannel,
    bot_member: discord.Member,
) -> str | None:
    permissions = channel.permissions_for(bot_member)
    if not permissions.view_channel or not permissions.send_messages or not permissions.embed_links:
        return (
            f"The bot cannot post embeds in {channel.mention}. "
            "Grant View Channel, Send Messages, and Embed Links there."
        )
    return None


def format_sticky_location(channel_id: int, message_id: int) -> str:
    return f"{channel_id}:{message_id}"


def format_sticky_message_id_only(_channel_id: int, message_id: int) -> str:
    return str(message_id)


async def _send_sticky_embed(
    channel: discord.TextChannel,
    embed: discord.Embed,
    view: discord.ui.View | None,
) -> discord.Message:
    if view is None:
        return await channel.send(embed=embed, silent=True)
    return await channel.send(embed=embed, view=view, silent=True)


async def _edit_sticky_embed(
    message: discord.Message,
    embed: discord.Embed,
    view: discord.ui.View | None,
) -> None:
    if view is None:
        await message.edit(embed=embed)
        return
    await message.edit(embed=embed, view=view)


@dataclass(frozen=True)
class StoredStickySyncResult:
    success: bool
    message: discord.Message | None = None
    updated: bool = False
    skipped: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class StoredStickyDefinition:
    """Configuration for hub stickies persisted via settings keys."""

    settings_key: str
    build_embed: Callable[[], discord.Embed]
    is_current: Callable[[discord.Embed], bool]
    refresh_current: (
        Callable[
            [discord.Message, discord.Embed, discord.ui.View],
            Awaitable[None],
        ]
        | None
    ) = None


def sticky_channel_manage_messages_error(
    channel: discord.TextChannel,
    bot_member: discord.Member,
) -> str | None:
    embed_error = sticky_channel_embed_permission_error(channel, bot_member)
    if embed_error is not None:
        return embed_error
    permissions = channel.permissions_for(bot_member)
    if not permissions.manage_messages:
        return (
            f"The bot cannot manage messages in {channel.mention}. "
            "Grant View Channel, Send Messages, Embed Links, and Manage Messages there."
        )
    return None


async def sync_stored_embed_sticky(
    channel: discord.TextChannel,
    bot_member: discord.Member,
    *,
    get_setting: Callable[[str], Awaitable[str | None]],
    set_setting: Callable[[str, str], Awaitable[None]],
    settings_key: str,
    desired_embed: discord.Embed,
    view: discord.ui.View | None,
    is_current: Callable[[discord.Embed], bool],
    refresh_current: Callable[
        [discord.Message, discord.Embed, discord.ui.View | None],
        Awaitable[None],
    ],
    wipe_channel: bool = False,
    permission_check: Callable[
        [discord.TextChannel, discord.Member],
        str | None,
    ] = sticky_channel_embed_permission_error,
    format_setting_value: Callable[[int, int], str] = format_sticky_location,
    after_send: Callable[[discord.Message], Awaitable[None]] | None = None,
) -> StoredStickySyncResult:
    """Fetch-or-send sticky embed flow shared by hub stickies with settings persistence."""
    permission_error = permission_check(channel, bot_member)
    if permission_error is not None:
        return StoredStickySyncResult(
            success=False,
            skipped=True,
            reason=permission_error,
        )

    if wipe_channel:
        from bot.core.discord.cleanup import wipe_text_channel

        _deleted, wipe_error = await wipe_text_channel(channel, bot_member)
        if wipe_error is not None:
            return StoredStickySyncResult(success=False, reason=wipe_error)

        message = await _send_sticky_embed(channel, desired_embed, view)
        if after_send is not None:
            await after_send(message)
        await set_setting(
            settings_key,
            format_setting_value(channel.id, message.id),
        )
        return StoredStickySyncResult(success=True, message=message, updated=True)

    stored_raw = await get_setting(settings_key)
    existing: discord.Message | None = None
    if stored_raw:
        try:
            message_id = int(stored_raw.split(":")[-1])
            existing = await channel.fetch_message(message_id)
        except (ValueError, discord.HTTPException):
            existing = None

    if existing is not None and existing.author.id == bot_member.id and existing.embeds:
        existing_embed = existing.embeds[0]
        if is_current(existing_embed):
            await refresh_current(existing, desired_embed, view)
            await set_setting(
                settings_key,
                format_setting_value(channel.id, existing.id),
            )
            return StoredStickySyncResult(success=True, message=existing, skipped=True)

        try:
            await _edit_sticky_embed(existing, desired_embed, view)
            await set_setting(
                settings_key,
                format_setting_value(channel.id, existing.id),
            )
            return StoredStickySyncResult(success=True, message=existing, updated=True)
        except discord.HTTPException:
            try:
                await existing.delete()
            except discord.HTTPException:
                pass

    message = await _send_sticky_embed(channel, desired_embed, view)
    if after_send is not None:
        await after_send(message)
    await set_setting(settings_key, format_setting_value(channel.id, message.id))
    return StoredStickySyncResult(success=True, message=message, updated=True)


async def sync_stored_sticky(
    channel: discord.TextChannel,
    bot_member: discord.Member,
    view: discord.ui.View | None,
    *,
    get_setting: Callable[[str], Awaitable[str | None]],
    set_setting: Callable[[str, str], Awaitable[None]],
    definition: StoredStickyDefinition,
    wipe_channel: bool = False,
    permission_check: Callable[
        [discord.TextChannel, discord.Member],
        str | None,
    ] = sticky_channel_embed_permission_error,
    format_setting_value: Callable[[int, int], str] = format_sticky_location,
    after_send: Callable[[discord.Message], Awaitable[None]] | None = None,
) -> StoredStickySyncResult:
    async def _default_refresh(
        message: discord.Message,
        embed: discord.Embed,
        sticky_view: discord.ui.View | None,
    ) -> None:
        await _edit_sticky_embed(message, embed, sticky_view)

    refresh = definition.refresh_current or _default_refresh
    return await sync_stored_embed_sticky(
        channel,
        bot_member,
        get_setting=get_setting,
        set_setting=set_setting,
        settings_key=definition.settings_key,
        desired_embed=definition.build_embed(),
        view=view,
        is_current=definition.is_current,
        refresh_current=refresh,  # type: ignore[arg-type]
        wipe_channel=wipe_channel,
        permission_check=permission_check,
        format_setting_value=format_setting_value,
        after_send=after_send,
    )


@dataclass(frozen=True)
class FooterMarkerStickySyncResult:
    message: discord.Message | None = None
    created: bool = False
    updated: bool = False
    removed: bool = False


async def find_embed_sticky_by_footer_scan(
    channel: discord.abc.GuildChannel,
    *,
    bot_user_id: int,
    footer_marker: str,
    history_limit: int = SETUP_STICKY_HISTORY_LIMIT,
) -> discord.Message | None:
    if not hasattr(channel, "history"):
        return None
    marker = footer_marker.casefold()
    try:
        async for message in channel.history(limit=history_limit):
            if message.author.id != bot_user_id or not message.embeds:
                continue
            footer = (message.embeds[0].footer.text or "").casefold()
            if marker in footer:
                return cast(discord.Message, message)
    except discord.HTTPException:
        return None
    return None


async def resolve_embed_sticky_message(
    channel: discord.abc.GuildChannel,
    *,
    bot_user_id: int,
    message_id: int | None,
    footer_marker: str,
) -> discord.Message | None:
    if message_id is not None and hasattr(channel, "fetch_message"):
        try:
            return cast(
                discord.Message,
                await channel.fetch_message(message_id),
            )
        except discord.HTTPException:
            pass
    return await find_embed_sticky_by_footer_scan(
        channel,
        bot_user_id=bot_user_id,
        footer_marker=footer_marker,
    )


async def sync_footer_marker_embed_sticky(
    channel: discord.abc.GuildChannel,
    *,
    bot_user_id: int,
    stored_message_id: int | None,
    footer_marker: str,
    embed: discord.Embed,
    view: discord.ui.View | None = None,
    allow_create: bool,
    remove: bool,
) -> FooterMarkerStickySyncResult:
    """Refresh or remove subscription setup stickies located by footer marker."""
    if remove:
        message = await resolve_embed_sticky_message(
            channel,
            bot_user_id=bot_user_id,
            message_id=stored_message_id,
            footer_marker=footer_marker,
        )
        if message is not None:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
        return FooterMarkerStickySyncResult(removed=True)

    if not hasattr(channel, "send"):
        return FooterMarkerStickySyncResult()

    message = await resolve_embed_sticky_message(
        channel,
        bot_user_id=bot_user_id,
        message_id=stored_message_id,
        footer_marker=footer_marker,
    )
    if message is not None:
        try:
            await _edit_sticky_embed(message, embed, view)
            return FooterMarkerStickySyncResult(message=message, updated=True)
        except discord.HTTPException:
            logger.warning(
                "Could not refresh footer-marker sticky",
                extra={"channel_id": channel.id, "message_id": message.id},
            )

    if not allow_create:
        return FooterMarkerStickySyncResult()

    try:
        message = await channel.send(
            embed=embed,
            view=view,
            silent=True,
        )
    except discord.NotFound:
        logger.warning(
            "Could not create footer-marker sticky; channel missing",
            extra={"channel_id": getattr(channel, "id", None)},
        )
        return FooterMarkerStickySyncResult()
    except discord.HTTPException as exc:
        logger.warning(
            "Could not create footer-marker sticky",
            extra={"channel_id": getattr(channel, "id", None), "error": str(exc)},
        )
        return FooterMarkerStickySyncResult()
    return FooterMarkerStickySyncResult(message=message, created=True)
