from __future__ import annotations

import logging

import discord

logger = logging.getLogger(__name__)

_DELETABLE_CHANNEL_TYPES = (
    discord.TextChannel,
    discord.ForumChannel,
    discord.VoiceChannel,
    discord.CategoryChannel,
)


async def delete_channel(
    guild: discord.Guild,
    channel_id: int,
    *,
    label: str,
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
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException as exc:
        logger.warning(
            "Could not delete channel during cleanup",
            extra={"channel_id": channel_id, "label": label, "error": str(exc)},
        )
        return False


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
