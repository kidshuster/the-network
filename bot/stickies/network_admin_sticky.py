from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.messages import render_embed
from bot.stickies.sync import (
    StoredStickyDefinition,
    StoredStickySyncResult,
    sync_stored_sticky,
)

if TYPE_CHECKING:
    from bot.context import BotContext

logger = logging.getLogger(__name__)

NETWORK_ADMIN_VERSION = 1
NETWORK_ADMIN_SETTINGS_KEY = "hub_network_admin_sticky"
NETWORK_ADMIN_FOOTER_PREFIX = "The Network • network admin"


@dataclass(frozen=True)
class NetworkAdminStickyResult:
    success: bool
    message: discord.Message | None = None
    updated: bool = False
    skipped: bool = False
    reason: str | None = None


def build_network_admin_footer() -> str:
    return f"{NETWORK_ADMIN_FOOTER_PREFIX} • v{NETWORK_ADMIN_VERSION}"


async def build_network_admin_embed(context: BotContext) -> discord.Embed:
    networks = await context.store.networks.list_all()
    embed = render_embed("network_admin", version=NETWORK_ADMIN_VERSION)
    if not networks:
        embed.add_field(
            name="Registered networks",
            value="No networks yet. Click **Create Network** to register one.",
            inline=False,
        )
        return embed

    for network in networks[:25]:
        subs = await context.store.clients.list_subscriptions_by_network(network.id)
        embed.add_field(
            name=f"{network.display_name} (`{network.key}`)",
            value=f"Subscriptions: **{len(subs)}**",
            inline=False,
        )
    if len(networks) > 25:
        embed.set_footer(text=f"{build_network_admin_footer()} · showing 25 of {len(networks)}")
    return embed


async def refresh_network_admin_message(
    context: BotContext,
    guild: discord.Guild,
    channel: discord.TextChannel,
    view: discord.ui.View,
    *,
    message_id: int | None = None,
) -> discord.Message | None:
    embed = await build_network_admin_embed(context)

    if message_id is not None:
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=embed, view=view)
            return message
        except discord.HTTPException:
            pass

    return await channel.send(embed=embed, view=view, silent=True)


async def refresh_network_admin_sticky_from_settings(
    context: BotContext,
    guild: discord.Guild,
    view: discord.ui.View,
) -> None:
    from bot.hub.resolve import resolve_network_admin_channel

    channel = resolve_network_admin_channel(guild)
    if channel is None:
        return

    raw = await context.store.settings.get(NETWORK_ADMIN_SETTINGS_KEY)
    message_id: int | None = None
    if raw and ":" in raw:
        try:
            message_id = int(raw.split(":")[-1])
        except ValueError:
            message_id = None

    message = await refresh_network_admin_message(
        context,
        guild,
        channel,
        view,
        message_id=message_id,
    )
    if message is not None:
        await context.store.settings.set(
            NETWORK_ADMIN_SETTINGS_KEY,
            f"{channel.id}:{message.id}",
        )


def _network_admin_result(result: StoredStickySyncResult) -> NetworkAdminStickyResult:
    return NetworkAdminStickyResult(
        success=result.success,
        message=result.message,
        updated=result.updated,
        skipped=result.skipped,
        reason=result.reason,
    )


async def sync_network_admin_sticky(
    guild: discord.Guild,
    bot_member: discord.Member,
    channel: discord.TextChannel,
    context: BotContext,
    view: discord.ui.View,
    *,
    get_setting: Callable[[str], Awaitable[str | None]],
    set_setting: Callable[[str, str], Awaitable[None]],
    wipe_channel: bool = False,
) -> NetworkAdminStickyResult:
    desired_embed = await build_network_admin_embed(context)
    footer = build_network_admin_footer()
    if desired_embed.footer and desired_embed.footer.text:
        footer = desired_embed.footer.text

    async def refresh_current(
        message: discord.Message,
        embed: discord.Embed,
        sticky_view: discord.ui.View,
    ) -> None:
        await message.edit(embed=embed, view=sticky_view)

    definition = StoredStickyDefinition(
        settings_key=NETWORK_ADMIN_SETTINGS_KEY,
        build_embed=lambda: desired_embed,
        is_current=lambda existing_embed: (
            (existing_embed.footer.text if existing_embed.footer else "") == footer
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
    return _network_admin_result(result)
