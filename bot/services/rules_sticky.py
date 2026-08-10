from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from bot.services.sticky_sync import (
    format_sticky_message_id_only,
    sticky_channel_manage_messages_error,
    sync_stored_embed_sticky,
)

logger = logging.getLogger(__name__)

RULES_STICKY_VERSION = 2
RULES_STICKY_SETTINGS_KEY = "hub_rules_sticky_message"
RULES_FOOTER = f"The Network • hub rules • v{RULES_STICKY_VERSION}"


@dataclass(frozen=True)
class RulesStickyResult:
    success: bool
    message: discord.Message | None = None
    updated: bool = False
    skipped: bool = False
    reason: str | None = None


def resolve_rules_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel = guild.rules_channel
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


def build_rules_embed() -> discord.Embed:
    from bot.messages import render_embed

    return render_embed("hub_rules", version=RULES_STICKY_VERSION)


async def _pin_if_possible(message: discord.Message) -> None:
    try:
        await message.pin(reason="The Network hub rules sticky")
    except discord.HTTPException:
        logger.debug(
            "Could not pin rules sticky message",
            extra={"channel_id": message.channel.id, "message_id": message.id},
        )


async def sync_rules_sticky(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    get_setting: Callable[[str], Awaitable[str | None]],
    set_setting: Callable[[str, str], Awaitable[None]],
) -> RulesStickyResult:
    rules_channel = resolve_rules_channel(guild)
    if rules_channel is None:
        return RulesStickyResult(
            success=False,
            skipped=True,
            reason=(
                "This guild has no Community rules channel configured. "
                "Set one under Server Settings → Enable Community."
            ),
        )

    async def _noop_refresh(
        _message: discord.Message,
        _embed: discord.Embed,
        _view: discord.ui.View | None,
    ) -> None:
        return None

    result = await sync_stored_embed_sticky(
        rules_channel,
        bot_member,
        get_setting=get_setting,
        set_setting=set_setting,
        settings_key=RULES_STICKY_SETTINGS_KEY,
        desired_embed=build_rules_embed(),
        view=None,
        is_current=lambda _embed: False,
        refresh_current=_noop_refresh,
        wipe_channel=True,
        permission_check=sticky_channel_manage_messages_error,
        format_setting_value=format_sticky_message_id_only,
        after_send=_pin_if_possible,
    )
    return RulesStickyResult(
        success=result.success,
        message=result.message,
        updated=result.updated,
        skipped=result.skipped,
        reason=result.reason,
    )
