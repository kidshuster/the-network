from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.app.recipes.registry import recipe
from bot.app.templates import render_embed
from bot.config import Settings
from bot.core.networks.roles import resolve_operator_role_by_name
from bot.features.channels.resolve import (
    HUB_CATEGORY_MODERATION,
    HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
    resolve_hub_category,
    resolve_hub_channel,
)

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot
    from bot.app.context import BotContext
    from bot.app.recipes.runtime import RecipeContext

logger = logging.getLogger(__name__)

_GUIDE_FOOTER = "hub announcements guide"
_SINGLE_LINE_PREFIX_RE = re.compile(r"^\[([a-z0-9_-]+)\]$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedAnnouncement:
    network_keys: tuple[str, ...]
    body: str
    error: str | None = None


@dataclass(frozen=True)
class DispatchResult:
    success: bool
    networks_attempted: tuple[str, ...]
    networks_relayed: tuple[str, ...]
    errors: tuple[str, ...]


def parse_announcement_content(
    content: str,
    *,
    available_keys: set[str],
) -> ParsedAnnouncement:
    lines = (content or "").splitlines()
    if lines:
        match = _SINGLE_LINE_PREFIX_RE.match(lines[0].strip())
        if match is not None:
            key = match.group(1).casefold()
            body = "\n".join(lines[1:]).strip()
            if key not in available_keys:
                available = ", ".join(f"`{item}`" for item in sorted(available_keys))
                return ParsedAnnouncement(
                    (),
                    body,
                    f"Unknown network `{key}`. Available: {available or '(none)'}.",
                )
            return ParsedAnnouncement((key,), body)
    return ParsedAnnouncement(tuple(sorted(available_keys)), (content or "").strip())


def can_post_hub_announcement(
    member: discord.Member,
    guild: discord.Guild,
    settings: Settings,
) -> bool:
    from bot.features.channels.resolve import resolve_human_moderator_role

    operator = resolve_operator_role_by_name(
        guild,
        role_name=settings.network_operator_role_name,
    )
    moderator = resolve_human_moderator_role(guild)
    return bool(
        (operator is not None and operator in member.roles)
        or (moderator is not None and moderator in member.roles)
        or member.guild_permissions.manage_guild
    )


def _resolve_network_announcements_channel(
    guild: discord.Guild,
) -> discord.TextChannel | None:
    mod_category = resolve_hub_category(guild, HUB_CATEGORY_MODERATION)
    return resolve_hub_channel(
        guild,
        HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
        category_id=None if mod_category is None else mod_category.id,
        include_announcement=False,
    )


async def sync_announcements_guide(
    guild: discord.Guild,
    bot_member: discord.Member,
) -> None:
    channel = _resolve_network_announcements_channel(guild)
    if channel is None:
        return
    embed = render_embed("hub_announcements_guide")
    try:
        async for message in channel.history(limit=20):
            footer = message.embeds[0].footer.text if message.embeds else ""
            if message.author.id == bot_member.id and _GUIDE_FOOTER in (footer or "").casefold():
                await message.edit(embed=embed)
                return
        await channel.send(embed=embed, silent=True)
    except discord.HTTPException:
        logger.warning("Could not sync announcements guide", extra={"channel_id": channel.id})


async def dispatch_system_announcement(
    context: BotContext,
    guild: discord.Guild,
    message: discord.Message,
) -> DispatchResult:
    networks = [network for network in await context.store.networks.list_all() if network.enabled]
    by_key = {network.key: network for network in networks}
    parsed = parse_announcement_content(message.content or "", available_keys=set(by_key))
    if parsed.error is not None:
        return DispatchResult(False, (), (), (parsed.error,))
    if not parsed.body and not message.embeds and not message.attachments:
        return DispatchResult(False, (), (), ("Message is empty.",))

    relayed: list[str] = []
    errors: list[str] = []
    for key in parsed.network_keys:
        network = by_key[key]
        result = await context.relay_service.deliver_system_announcement(
            message,
            network_id=network.id,
            body=parsed.body,
        )
        if result.success:
            relayed.append(key)
        else:
            errors.append(f"`{key}`: {result.error or 'no relay destinations'}")
    return DispatchResult(
        success=bool(relayed) and not errors,
        networks_attempted=parsed.network_keys,
        networks_relayed=tuple(relayed),
        errors=tuple(errors),
    )


async def handle_network_announcements_message(
    bot: NetworkRelayBot,
    message: discord.Message,
) -> None:
    context = bot.bot_context
    guild = message.guild
    if context is None or guild is None or message.author.bot:
        return
    channel = _resolve_network_announcements_channel(guild)
    if channel is None or message.channel.id != channel.id:
        return
    if not isinstance(message.author, discord.Member):
        return
    if not can_post_hub_announcement(message.author, guild, bot.settings):
        return

    result = await dispatch_system_announcement(context, guild, message)
    if result.networks_relayed:
        description = "Relayed to " + ", ".join(f"`{key}`" for key in result.networks_relayed)
        colour = "green" if not result.errors else "yellow"
    else:
        description = result.errors[0] if result.errors else "Announcement was not relayed."
        colour = "red"
    try:
        await message.reply(
            embed=render_embed(
                "review_success",
                label="Announcements",
                colour=colour,
                description=description,
            ),
            mention_author=False,
        )
    except discord.HTTPException:
        logger.warning("Could not post announcement dispatch result")


@recipe("hub.handle_announcement")
async def handle_announcement_recipe(
    recipe_context: RecipeContext,
    *,
    message: discord.Message,
) -> None:
    await handle_network_announcements_message(recipe_context.bot, message)
