from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

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
    embed = discord.Embed(
        title="📡 The Network — Relay Rules",
        description=(
            "Servers linked to a network **publish to every participant**. "
            "What you post in your announcement channel is relayed across the whole network — "
            "treat it like a shared megaphone, not your personal spam cannon. 📢"
        ),
        colour=discord.Colour.gold(),
    )
    embed.add_field(
        name="🚫 Don't flood the network",
        value=(
            "No spam, no junk, no constant low-effort posts. "
            "If you abuse the relay, you'll be **removed from the network** — no drama, just gone."
        ),
        inline=False,
    )
    embed.add_field(
        name="🔒 Lock down your announcement channel",
        value=(
            "On **your** server, restrict who can post in your announcement channel — "
            "**officers and moderators only**. One careless member posting for everyone "
            "is how networks get burned."
        ),
        inline=False,
    )
    embed.add_field(
        name="🎯 Post what matters",
        value=(
            "Updates, events, ops, recruitment — things partner servers actually want to see. "
            "Not memes, not ads, not noise."
        ),
        inline=False,
    )
    embed.add_field(
        name="⚖️ Play by Discord's rules too",
        value=(
            "Illegal content, hate, scams, and ToS violations get you bounced from the network "
            "and reported. Don't be that server."
        ),
        inline=False,
    )
    embed.add_field(
        name="🛠️ Joining a network",
        value=(
            "Each network has a **join-** channel under **The Network** category. "
            "Open yours and click **Join Server** when you're ready to link up."
        ),
        inline=False,
    )
    embed.set_footer(text=RULES_FOOTER)
    return embed


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

    permissions = rules_channel.permissions_for(bot_member)
    required = (
        permissions.view_channel,
        permissions.send_messages,
        permissions.embed_links,
        permissions.manage_messages,
    )
    if not all(required):
        return RulesStickyResult(
            success=False,
            skipped=True,
            reason=(
                f"The bot cannot manage messages in {rules_channel.mention}. "
                "Grant View Channel, Send Messages, Embed Links, and Manage Messages there."
            ),
        )

    from bot.services.discord_cleanup import wipe_text_channel

    _deleted, wipe_error = await wipe_text_channel(rules_channel, bot_member)
    if wipe_error is not None:
        return RulesStickyResult(success=False, reason=wipe_error)

    embed = build_rules_embed()
    message = await rules_channel.send(embed=embed)
    await _pin_if_possible(message)
    await set_setting(RULES_STICKY_SETTINGS_KEY, str(message.id))
    return RulesStickyResult(success=True, message=message, updated=True)
