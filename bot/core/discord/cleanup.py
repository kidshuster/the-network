from __future__ import annotations

import logging
from collections.abc import Sequence

import discord

logger = logging.getLogger(__name__)

_DELETABLE_CHANNEL_TYPES = (
    discord.TextChannel,
    discord.ForumChannel,
    discord.VoiceChannel,
    discord.CategoryChannel,
)


async def wipe_text_channel(
    channel: discord.TextChannel,
    bot_member: discord.Member,
) -> tuple[int, str | None]:
    """Delete all messages in a text channel. Returns (deleted_count, error)."""
    permissions = channel.permissions_for(bot_member)
    if not permissions.view_channel:
        return 0, "The bot needs **View Channel** to clear this channel."
    if not permissions.manage_messages:
        return 0, "The bot needs **Manage Messages** to clear this channel."

    deleted = 0
    while True:
        purged = await channel.purge(limit=100)
        if not purged:
            break
        deleted += len(purged)

    async for message in channel.history(limit=None):
        try:
            await message.delete()
            deleted += 1
        except discord.HTTPException as exc:
            logger.warning(
                "Could not delete message while wiping channel",
                extra={"channel_id": channel.id, "message_id": message.id, "error": str(exc)},
            )
    return deleted, None


async def delete_channel(
    guild: discord.Guild,
    channel_id: int,
    *,
    label: str,
    reorder: Sequence[discord.abc.GuildChannel] | None = None,
) -> bool:
    channel: discord.abc.GuildChannel | None = guild.get_channel(channel_id)
    if channel is None:
        try:
            fetched = await guild.fetch_channel(channel_id)
        except discord.NotFound:
            return False
        except discord.HTTPException as exc:
            logger.warning(
                "Could not fetch channel for cleanup",
                extra={"channel_id": channel_id, "label": label, "error": str(exc)},
            )
            return False
        if not isinstance(fetched, _DELETABLE_CHANNEL_TYPES):
            return False
        channel = fetched

    try:
        await channel.delete(reason=f"The Network: {label} cleanup")
    except discord.NotFound:
        return False
    except discord.HTTPException as exc:
        logger.warning(
            "Could not delete channel during cleanup",
            extra={"channel_id": channel_id, "label": label, "error": str(exc)},
        )
        return False

    if reorder:
        from bot.core.channels.order import align_positions

        await align_positions(
            reorder,
            reason=f"The Network: {label} order",
        )
    return True


async def delete_role(
    guild: discord.Guild,
    role_id: int,
    *,
    label: str,
) -> bool:
    role = guild.get_role(role_id)
    if role is None:
        return False
    try:
        await role.delete(reason=f"The Network: {label} cleanup")
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException as exc:
        logger.warning(
            "Could not delete role during cleanup",
            extra={"role_id": role_id, "label": label, "error": str(exc)},
        )
        return False
