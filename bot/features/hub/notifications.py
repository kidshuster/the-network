from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from bot.features.hub.result import GuildInitResult

_HUB_CHANNEL_TYPES = (
    discord.TextChannel,
    discord.VoiceChannel,
    discord.CategoryChannel,
    discord.StageChannel,
    discord.ForumChannel,
)


def count_hub_guild_channels(guild: discord.Guild) -> int:
    return sum(1 for channel in guild.channels if isinstance(channel, _HUB_CHANNEL_TYPES))


async def ensure_guild_only_mention_notifications(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    reason: str,
) -> tuple[bool, str | None]:
    """Set guild default notifications to Only @mentions.

    Discord applies this default to all channels for members using server
    notification settings (per-member channel overrides cannot be changed by bots).
    """
    if not bot_member.guild_permissions.manage_guild:
        return False, "bot needs **Manage Server**"

    if guild.default_notifications == discord.NotificationLevel.only_mentions:
        return False, None

    await guild.edit(
        default_notifications=discord.NotificationLevel.only_mentions,
        reason=reason,
    )
    return True, None


async def sync_guild_notification_policy(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    reason: str,
    result: GuildInitResult | None = None,
) -> None:
    """Ensure the hub guild uses Only @mentions for default notifications."""
    try:
        changed, error = await ensure_guild_only_mention_notifications(
            guild,
            bot_member,
            reason=reason,
        )
    except discord.HTTPException as exc:
        message = f"Could not set server default notifications to **Only @mentions**: {exc}"
        if result is not None:
            result.notes.append(message)
        return

    channel_count = count_hub_guild_channels(guild)
    if error is not None:
        message = f"Could not set server default notifications to **Only @mentions** ({error})."
    elif changed:
        message = (
            "Server default notifications set to **Only @mentions**. "
            f"Applies guild-wide to **{channel_count}** channel(s) for members "
            "using server defaults. Bot posts stay silent except join requests "
            "in **#join-requests**."
        )
    else:
        message = (
            "Server default notifications already **Only @mentions** "
            f"(**{channel_count}** channel(s) use the guild default)."
        )

    if result is not None:
        result.notes.append(message)
