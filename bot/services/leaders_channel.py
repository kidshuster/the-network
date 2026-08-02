from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.services.guild_layout import CHANNEL_LEADERS, resolve_leaders_channel
from bot.services.guild_permissions import (
    build_leaders_channel_overwrites,
    filter_configurable_overwrites,
)

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

LEADERS_CHANNEL_SETTINGS_KEY = "hub_leaders_channel"


async def ensure_leaders_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    *,
    network_category: discord.CategoryChannel,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> discord.TextChannel | None:
    """Create or sync #leaders under The Network with all client roles."""
    from bot.services.guild_permissions import create_text_channel_with_overwrites

    clients = [
        client
        for client in await context.client_repo.list_all()
        if client.guild_id == guild.id
    ]
    client_roles: list[discord.Role] = []
    for client in clients:
        role = guild.get_role(client.client_role_id)
        if role is not None:
            client_roles.append(role)

    overwrites = filter_configurable_overwrites(
        bot_member,
        build_leaders_channel_overwrites(
            guild,
            bot_member,
            client_roles,
            access_role,
            human_moderator_role,
        ),
        for_channel=True,
    )

    channel = resolve_leaders_channel(guild)
    if channel is None:
        try:
            channel = await create_text_channel_with_overwrites(
                guild,
                bot_member,
                name=CHANNEL_LEADERS,
                category=network_category,
                overwrites=overwrites,
                topic="Private channel for participating server leaders",
                reason="The Network guild init",
            )
        except discord.HTTPException:
            logger.warning("Could not create #leaders channel")
            return None
    else:
        if channel.category_id != network_category.id:
            try:
                await channel.edit(category=network_category, reason="The Network guild init")
            except discord.HTTPException:
                pass
        try:
            await channel.edit(overwrites=overwrites, reason="The Network leaders channel sync")
        except discord.HTTPException:
            logger.warning(
                "Could not sync #leaders overwrites",
                extra={"channel_id": channel.id},
            )

    await context.settings_repo.set(LEADERS_CHANNEL_SETTINGS_KEY, str(channel.id))
    return channel


async def grant_leaders_channel_access(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    client_role: discord.Role,
    *,
    access_role_name: str,
) -> None:
    """Add a newly approved client role to #leaders."""
    from bot.services.network_provision import resolve_access_role

    channel = resolve_leaders_channel(guild)
    if channel is None:
        stored = await context.settings_repo.get(LEADERS_CHANNEL_SETTINGS_KEY)
        if stored:
            ch = guild.get_channel(int(stored))
            if isinstance(ch, discord.TextChannel):
                channel = ch
    if channel is None:
        return

    access_role = resolve_access_role(guild, role_name=access_role_name)
    if access_role is None:
        return

    human_moderator_role = None
    from bot.services.guild_layout import resolve_human_moderator_role

    human_moderator_role = resolve_human_moderator_role(guild)

    clients = [
        client
        for client in await context.client_repo.list_all()
        if client.guild_id == guild.id
    ]
    client_roles: list[discord.Role] = []
    for client in clients:
        role = guild.get_role(client.client_role_id)
        if role is not None:
            client_roles.append(role)
    if client_role not in client_roles:
        client_roles.append(client_role)

    overwrites = filter_configurable_overwrites(
        bot_member,
        build_leaders_channel_overwrites(
            guild,
            bot_member,
            client_roles,
            access_role,
            human_moderator_role,
        ),
        for_channel=True,
    )
    try:
        await channel.edit(overwrites=overwrites, reason="The Network client approved")
    except discord.HTTPException:
        logger.warning(
            "Could not grant #leaders access for new client role",
            extra={"role_id": client_role.id},
        )
