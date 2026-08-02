from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.messages import render_embed

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
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
    networks = await context.network_repo.list_all()
    embed = render_embed("network_admin", version=NETWORK_ADMIN_VERSION)
    if not networks:
        embed.add_field(
            name="Registered networks",
            value="No networks yet. Click **Create Network** to register one.",
            inline=False,
        )
        return embed

    for network in networks[:25]:
        subs = await context.client_repo.list_subscriptions_by_network(network.id)
        status = "enabled" if network.enabled else "disabled"
        embed.add_field(
            name=f"{network.display_name} (`{network.key}`)",
            value=f"Status: **{status}** · Subscriptions: **{len(subs)}**",
            inline=False,
        )
    if len(networks) > 25:
        embed.set_footer(text=f"{build_network_admin_footer()} · showing 25 of {len(networks)}")
    return embed


async def refresh_network_admin_message(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    channel: discord.TextChannel,
    *,
    message_id: int | None = None,
) -> discord.Message | None:
    from bot.ui.network_admin_views import NetworkAdminView

    embed = await build_network_admin_embed(context)
    view = NetworkAdminView(bot)
    bot.add_view(view)

    if message_id is not None:
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=embed, view=view)
            return message
        except discord.HTTPException:
            pass

    return await channel.send(embed=embed, view=view, silent=True)


async def refresh_network_admin_sticky_from_settings(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
) -> None:
    from bot.services.guild_layout import resolve_network_admin_channel

    channel = resolve_network_admin_channel(guild)
    if channel is None:
        return

    raw = await context.settings_repo.get(NETWORK_ADMIN_SETTINGS_KEY)
    message_id: int | None = None
    if raw and ":" in raw:
        try:
            message_id = int(raw.split(":")[-1])
        except ValueError:
            message_id = None

    message = await refresh_network_admin_message(
        bot,
        context,
        guild,
        channel,
        message_id=message_id,
    )
    if message is not None:
        await context.settings_repo.set(
            NETWORK_ADMIN_SETTINGS_KEY,
            f"{channel.id}:{message.id}",
        )


async def sync_network_admin_sticky(
    guild: discord.Guild,
    bot_member: discord.Member,
    bot: NetworkRelayBot,
    channel: discord.TextChannel,
    context: BotContext,
    *,
    get_setting: Callable[[str], Awaitable[str | None]],
    set_setting: Callable[[str, str], Awaitable[None]],
    wipe_channel: bool = False,
) -> NetworkAdminStickyResult:
    from bot.ui.network_admin_views import NetworkAdminView

    permissions = channel.permissions_for(bot_member)
    if not permissions.view_channel or not permissions.send_messages or not permissions.embed_links:
        return NetworkAdminStickyResult(
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
            return NetworkAdminStickyResult(success=False, reason=wipe_error)

    desired_embed = await build_network_admin_embed(context)
    footer = build_network_admin_footer()
    if desired_embed.footer and desired_embed.footer.text:
        footer = desired_embed.footer.text

    view = NetworkAdminView(bot)
    bot.add_view(view)

    if wipe_channel:
        message = await channel.send(embed=desired_embed, view=view, silent=True)
        await set_setting(NETWORK_ADMIN_SETTINGS_KEY, f"{channel.id}:{message.id}")
        return NetworkAdminStickyResult(success=True, message=message, updated=True)

    stored_raw = await get_setting(NETWORK_ADMIN_SETTINGS_KEY)
    existing: discord.Message | None = None
    if stored_raw:
        try:
            message_id = int(stored_raw.split(":")[-1])
            existing = await channel.fetch_message(message_id)
        except (ValueError, discord.HTTPException):
            existing = None

    if existing is not None and existing.author.id == bot_member.id and existing.embeds:
        existing_footer = existing.embeds[0].footer.text if existing.embeds[0].footer else ""
        if existing_footer == footer:
            await existing.edit(embed=desired_embed, view=view)
            await set_setting(NETWORK_ADMIN_SETTINGS_KEY, f"{channel.id}:{existing.id}")
            return NetworkAdminStickyResult(success=True, message=existing, skipped=True)

        try:
            await existing.edit(embed=desired_embed, view=view)
            await set_setting(NETWORK_ADMIN_SETTINGS_KEY, f"{channel.id}:{existing.id}")
            return NetworkAdminStickyResult(success=True, message=existing, updated=True)
        except discord.HTTPException:
            try:
                await existing.delete()
            except discord.HTTPException:
                pass

    message = await channel.send(embed=desired_embed, view=view, silent=True)
    await set_setting(NETWORK_ADMIN_SETTINGS_KEY, f"{channel.id}:{message.id}")
    return NetworkAdminStickyResult(success=True, message=message, updated=True)
