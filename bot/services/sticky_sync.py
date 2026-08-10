from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord


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


@dataclass(frozen=True)
class StoredStickySyncResult:
    success: bool
    message: discord.Message | None = None
    updated: bool = False
    skipped: bool = False
    reason: str | None = None


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
    view: discord.ui.View,
    is_current: Callable[[discord.Embed], bool],
    refresh_current: Callable[
        [discord.Message, discord.Embed, discord.ui.View],
        Awaitable[None],
    ],
    wipe_channel: bool = False,
) -> StoredStickySyncResult:
    """Fetch-or-send sticky embed flow shared by hub stickies with settings persistence."""
    permission_error = sticky_channel_embed_permission_error(channel, bot_member)
    if permission_error is not None:
        return StoredStickySyncResult(
            success=False,
            skipped=True,
            reason=permission_error,
        )

    if wipe_channel:
        from bot.services.discord_cleanup import wipe_text_channel

        _deleted, wipe_error = await wipe_text_channel(channel, bot_member)
        if wipe_error is not None:
            return StoredStickySyncResult(success=False, reason=wipe_error)

        message = await channel.send(embed=desired_embed, view=view, silent=True)
        await set_setting(settings_key, f"{channel.id}:{message.id}")
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
            await set_setting(settings_key, f"{channel.id}:{existing.id}")
            return StoredStickySyncResult(success=True, message=existing, skipped=True)

        try:
            await existing.edit(embed=desired_embed, view=view)
            await set_setting(settings_key, f"{channel.id}:{existing.id}")
            return StoredStickySyncResult(success=True, message=existing, updated=True)
        except discord.HTTPException:
            try:
                await existing.delete()
            except discord.HTTPException:
                pass

    message = await channel.send(embed=desired_embed, view=view, silent=True)
    await set_setting(settings_key, f"{channel.id}:{message.id}")
    return StoredStickySyncResult(success=True, message=message, updated=True)
