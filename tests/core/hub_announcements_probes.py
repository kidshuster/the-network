from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.features.channels.resolve import resolve_network_announcements_channel
from bot.features.hub.announcements import dispatch_system_announcement
from tests.core.provision_flow import ensure_smoke_network_key

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot
    from bot.app.context import BotContext


@dataclass(frozen=True)
class HubAnnouncementsSmokeResult:
    subscriber_server_name: str
    network_key: str


async def run_hub_announcements_smoke_flow(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
) -> HubAnnouncementsSmokeResult:
    """Exercise the direct announcement dispatcher without a synthetic client."""
    channel = resolve_network_announcements_channel(guild)
    if channel is None:
        raise RuntimeError("#network-announcements is missing")
    network_key = await ensure_smoke_network_key(context, bot, guild)
    message = await channel.send(f"[{network_key}]\nHub announcement smoke probe", silent=True)
    result = await dispatch_system_announcement(context, guild, message)
    try:
        await message.delete()
    except discord.HTTPException:
        pass
    if not result.success:
        raise RuntimeError("Announcement dispatch failed: " + "; ".join(result.errors))
    return HubAnnouncementsSmokeResult(
        subscriber_server_name="direct-dispatch",
        network_key=network_key,
    )
