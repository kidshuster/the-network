from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.domain.network import Network
from bot.services.guild_channels import resolve_network_join_channel
from bot.ui.join_views import JoinServerView

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)

HOW_TO_JOIN_VERSION = 6
HOW_TO_JOIN_FOOTER_PREFIX = "The Network • how to join"


@dataclass(frozen=True)
class HowToJoinStickyResult:
    success: bool
    message: discord.Message | None = None
    updated: bool = False
    skipped: bool = False
    reason: str | None = None


# Backwards-compatible alias for existing imports
JoinStickyResult = HowToJoinStickyResult


def how_to_join_sticky_settings_key(network_key: str) -> str:
    return f"how_to_join_sticky_message:{network_key}"


@dataclass(frozen=True)
class HowToJoinStickyLocation:
    channel_id: int
    message_id: int


def format_how_to_join_sticky_location(channel_id: int, message_id: int) -> str:
    return f"{channel_id}:{message_id}"


def parse_how_to_join_sticky_location(
    raw: str | None,
    *,
    fallback_channel_id: int | None = None,
) -> HowToJoinStickyLocation | None:
    if raw is None:
        return None
    if ":" in raw:
        channel_part, message_part = raw.split(":", 1)
        return HowToJoinStickyLocation(int(channel_part), int(message_part))
    if fallback_channel_id is not None:
        return HowToJoinStickyLocation(fallback_channel_id, int(raw))
    return None


def build_how_to_join_footer(network_id: int) -> str:
    return f"{HOW_TO_JOIN_FOOTER_PREFIX} • {network_id} • v{HOW_TO_JOIN_VERSION}"


def join_sticky_settings_key(network_key: str) -> str:
    """Legacy settings key — kept for one-time migration reads."""
    return f"join_sticky_message:{network_key}"


def embed_content_signature(embed: discord.Embed) -> str:
    payload = {
        "title": embed.title,
        "description": embed.description,
        "fields": [(field.name, field.value, field.inline) for field in embed.fields],
        "footer": embed.footer.text if embed.footer else None,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_how_to_join_embed(network: Network) -> discord.Embed:
    embed = discord.Embed(
        title=f"How to join {network.display_name}",
        description=(
            "Set up **your Discord server** using the steps below, then click **Join Server** "
            "to request hub access. Moderators review submissions in their private area."
        ),
        colour=discord.Colour.green(),
    )
    embed.add_field(
        name="1. Enable Community on your server",
        value=(
            "On your server, open **Server Settings → Enable Community** and complete the "
            "setup checklist (rules, verification, and a public updates channel)."
        ),
        inline=False,
    )
    embed.add_field(
        name="2. Create an announcement channel",
        value=(
            "Still on your server: **Server Settings → Channels → Create Channel → "
            "Announcement**. Publish network-bound posts from this channel."
        ),
        inline=False,
    )
    embed.add_field(
        name="3. Request hub access",
        value=(
            "Click **Join Server** below and submit your server name, display name, and "
            "a profile image. You only need read access in this hub until you are approved."
        ),
        inline=False,
    )
    embed.add_field(
        name="4. Connect your announcement channel (after approval)",
        value=(
            f"You will receive one **feed channel** under **{network.display_name} Feed** "
            "with a profile card that stays at the bottom of the channel plus your relay feed. "
            "**Subscribe to Me!** (Channel Follow), and select the announcement channel "
            "from step 2 so your posts relay into the network."
        ),
        inline=False,
    )
    embed.add_field(
        name="5. Update your profile",
        value=(
            "Use the **Edit Profile** button on that card to change your "
            "display name or profile image."
        ),
        inline=False,
    )
    embed.add_field(
        name="Published relays",
        value=f"<#{network.output_channel_id}>",
        inline=False,
    )
    embed.set_footer(text=build_how_to_join_footer(network.id))
    return embed


def build_join_requests_embed(network: Network) -> discord.Embed:
    """Backwards-compatible alias."""
    return build_how_to_join_embed(network)


async def _fetch_stored_message(
    channel: discord.TextChannel,
    message_id: int,
) -> discord.Message | None:
    try:
        return await channel.fetch_message(message_id)
    except discord.HTTPException:
        return None


async def _resolve_stored_sticky_location(
    get_setting: Callable[[str], Awaitable[str | None]],
    network_key: str,
    *,
    fallback_channel_id: int | None = None,
) -> HowToJoinStickyLocation | None:
    for key_fn in (how_to_join_sticky_settings_key, join_sticky_settings_key):
        stored_raw = await get_setting(key_fn(network_key))
        location = parse_how_to_join_sticky_location(
            stored_raw,
            fallback_channel_id=fallback_channel_id,
        )
        if location is not None:
            return location
    return None


async def _fetch_stored_sticky_message(
    guild: discord.Guild,
    location: HowToJoinStickyLocation,
) -> discord.Message | None:
    channel = guild.get_channel(location.channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None
    return await _fetch_stored_message(channel, location.message_id)


async def post_how_to_join_message(
    channel: discord.TextChannel,
    network: Network,
    bot: NetworkRelayBot,
) -> discord.Message:
    view = JoinServerView(bot, network.key)
    bot.add_view(view)
    return await channel.send(embed=build_how_to_join_embed(network), view=view)


post_join_guide_message = post_how_to_join_message


async def refresh_how_to_join_guide(
    guild: discord.Guild,
    bot_member: discord.Member,
    network: Network,
    bot: NetworkRelayBot,
    channel: discord.TextChannel,
    *,
    get_setting: Callable[[str], Awaitable[str | None]],
    set_setting: Callable[[str, str], Awaitable[None]],
    wipe_channel: bool,
) -> HowToJoinStickyResult:
    permissions = channel.permissions_for(bot_member)
    if not permissions.view_channel or not permissions.send_messages or not permissions.embed_links:
        return HowToJoinStickyResult(
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
            return HowToJoinStickyResult(success=False, reason=wipe_error)

    message = await post_how_to_join_message(channel, network, bot)
    await set_setting(
        how_to_join_sticky_settings_key(network.key),
        format_how_to_join_sticky_location(channel.id, message.id),
    )
    return HowToJoinStickyResult(success=True, message=message, updated=True)


refresh_join_guide = refresh_how_to_join_guide


async def sync_network_how_to_join_sticky(
    guild: discord.Guild,
    bot_member: discord.Member,
    network: Network,
    bot: NetworkRelayBot,
    *,
    get_setting: Callable[[str], Awaitable[str | None]],
    set_setting: Callable[[str, str], Awaitable[None]],
    channel: discord.TextChannel | None = None,
    wipe_channel: bool = False,
) -> HowToJoinStickyResult:
    target_channel = channel or resolve_network_join_channel(guild, network)
    if target_channel is None:
        return HowToJoinStickyResult(
            success=False,
            skipped=True,
            reason=(
                f"No join channel found for `{network.key}`. "
                "Create the network again or run `/network sync-how-to-join` in a text channel."
            ),
        )

    if wipe_channel:
        return await refresh_how_to_join_guide(
            guild,
            bot_member,
            network,
            bot,
            target_channel,
            get_setting=get_setting,
            set_setting=set_setting,
            wipe_channel=True,
        )

    permissions = target_channel.permissions_for(bot_member)
    if not permissions.view_channel or not permissions.send_messages or not permissions.embed_links:
        return HowToJoinStickyResult(
            success=False,
            skipped=True,
            reason=(
                f"The bot cannot post embeds in {target_channel.mention}. "
                "Grant View Channel, Send Messages, and Embed Links there."
            ),
        )

    desired_embed = build_how_to_join_embed(network)
    desired_signature = embed_content_signature(desired_embed)
    stored_location = await _resolve_stored_sticky_location(
        get_setting,
        network.key,
        fallback_channel_id=target_channel.id,
    )

    existing: discord.Message | None = None
    if stored_location is not None:
        if stored_location.channel_id == target_channel.id:
            existing = await _fetch_stored_sticky_message(guild, stored_location)
        else:
            old_message = await _fetch_stored_sticky_message(guild, stored_location)
            if old_message is not None:
                try:
                    await old_message.delete()
                except discord.HTTPException:
                    pass

    view = JoinServerView(bot, network.key)
    bot.add_view(view)

    if existing is not None and existing.author.id == bot_member.id and existing.embeds:
        existing_signature = embed_content_signature(existing.embeds[0])
        footer = existing.embeds[0].footer.text if existing.embeds[0].footer else ""
        footer_ok = footer == build_how_to_join_footer(network.id)
        if footer_ok and existing_signature == desired_signature:
            await existing.edit(view=view)
            await set_setting(
                how_to_join_sticky_settings_key(network.key),
                format_how_to_join_sticky_location(target_channel.id, existing.id),
            )
            return HowToJoinStickyResult(success=True, message=existing, skipped=True)

        try:
            await existing.edit(embed=desired_embed, view=view)
            await set_setting(
                how_to_join_sticky_settings_key(network.key),
                format_how_to_join_sticky_location(target_channel.id, existing.id),
            )
            return HowToJoinStickyResult(success=True, message=existing, updated=True)
        except discord.HTTPException:
            try:
                await existing.delete()
            except discord.HTTPException:
                pass

    message = await target_channel.send(embed=desired_embed, view=view)
    await set_setting(
        how_to_join_sticky_settings_key(network.key),
        format_how_to_join_sticky_location(target_channel.id, message.id),
    )
    return HowToJoinStickyResult(success=True, message=message, updated=True)


sync_network_join_sticky = sync_network_how_to_join_sticky
