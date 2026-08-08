from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.services.guild_layout import (
    CATEGORY_LEADERS,
    CHANNEL_CHANGELOG,
    CHANNEL_LEADERS,
    resolve_changelog_channel,
    resolve_leaders_category,
    resolve_leaders_channel,
)
from bot.services.guild_permissions import (
    build_changelog_channel_overwrites,
    build_leaders_category_overwrites,
    build_leaders_channel_overwrites,
    filter_configurable_overwrites,
)

if TYPE_CHECKING:
    from bot.context import BotContext

logger = logging.getLogger(__name__)

LEADERS_CHANNEL_SETTINGS_KEY = "hub_leaders_channel"
CHANGELOG_CHANNEL_SETTINGS_KEY = "hub_changelog_channel"


async def _list_client_roles(
    guild: discord.Guild,
    context: BotContext,
    *,
    extra_role: discord.Role | None = None,
) -> list[discord.Role]:
    client_roles: list[discord.Role] = []
    for client in await context.client_repo.list_all():
        if client.guild_id != guild.id:
            continue
        role = guild.get_role(client.client_role_id)
        if role is not None:
            client_roles.append(role)
    if extra_role is not None and extra_role not in client_roles:
        client_roles.append(extra_role)
    return client_roles


async def _sync_leaders_permissions(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    extra_client_role: discord.Role | None = None,
    reason: str,
) -> tuple[discord.CategoryChannel | None, discord.TextChannel | None, discord.TextChannel | None]:
    from bot.services.guild_permissions import create_text_channel_with_overwrites

    client_roles = await _list_client_roles(
        guild,
        context,
        extra_role=extra_client_role,
    )

    category_overwrites = filter_configurable_overwrites(
        bot_member,
        build_leaders_category_overwrites(
            guild,
            bot_member,
            client_roles,
            access_role,
            human_moderator_role,
        ),
    )
    channel_overwrites = filter_configurable_overwrites(
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
    changelog_overwrites = filter_configurable_overwrites(
        bot_member,
        build_changelog_channel_overwrites(
            guild,
            bot_member,
            client_roles,
            access_role,
            human_moderator_role,
        ),
        for_channel=True,
    )

    category = resolve_leaders_category(guild)
    if category is None:
        try:
            category = await guild.create_category(
                name=CATEGORY_LEADERS,
                overwrites=category_overwrites,
                reason=reason,
            )
        except discord.HTTPException:
            logger.warning("Could not create Leaders category")
            return None, None, None
    else:
        try:
            await category.edit(overwrites=category_overwrites, reason=reason)
        except discord.HTTPException:
            logger.warning(
                "Could not sync Leaders category permissions",
                extra={"category_id": category.id},
            )

    channel = resolve_leaders_channel(guild)
    if channel is None:
        try:
            channel = await create_text_channel_with_overwrites(
                guild,
                bot_member,
                name=CHANNEL_LEADERS,
                category=category,
                overwrites=channel_overwrites,
                topic="Private channel for participating server leaders",
                reason=reason,
            )
        except discord.HTTPException:
            logger.warning("Could not create leaders channel")
            return category, None, None
    else:
        edit_kwargs: dict[str, object] = {
            "overwrites": channel_overwrites,
            "sync_permissions": False,
            "reason": reason,
        }
        if channel.category_id != category.id or channel.name != CHANNEL_LEADERS:
            edit_kwargs["category"] = category
            edit_kwargs["name"] = CHANNEL_LEADERS
        try:
            await channel.edit(**edit_kwargs)  # type: ignore[arg-type]
        except discord.HTTPException:
            logger.warning(
                "Could not sync leaders channel permissions",
                extra={"channel_id": channel.id},
            )

    changelog = resolve_changelog_channel(guild)
    if changelog is None:
        try:
            changelog = await create_text_channel_with_overwrites(
                guild,
                bot_member,
                name=CHANNEL_CHANGELOG,
                category=category,
                overwrites=changelog_overwrites,
                topic="Release notes for The Network bot",
                reason=reason,
                sync_permissions=False,
            )
        except discord.HTTPException:
            logger.warning("Could not create changelog channel")
            return category, channel, None
    else:
        changelog_edit_kwargs: dict[str, object] = {
            "overwrites": changelog_overwrites,
            "sync_permissions": False,
            "reason": reason,
        }
        if changelog.category_id != category.id or changelog.name != CHANNEL_CHANGELOG:
            changelog_edit_kwargs["category"] = category
            changelog_edit_kwargs["name"] = CHANNEL_CHANGELOG
        try:
            await changelog.edit(**changelog_edit_kwargs)  # type: ignore[arg-type]
        except discord.HTTPException:
            logger.warning(
                "Could not sync changelog channel permissions",
                extra={"channel_id": changelog.id},
            )

    return category, channel, changelog


async def ensure_leaders_channels(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    reason: str = "The Network guild init",
) -> tuple[discord.TextChannel | None, discord.TextChannel | None]:
    """Create or sync Leaders category channels for client roles."""
    _category, leaders, changelog = await _sync_leaders_permissions(
        guild,
        bot_member,
        context,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        reason=reason,
    )
    if leaders is not None:
        await context.settings_repo.set(LEADERS_CHANNEL_SETTINGS_KEY, str(leaders.id))
    if changelog is not None:
        await context.settings_repo.set(CHANGELOG_CHANNEL_SETTINGS_KEY, str(changelog.id))
    return leaders, changelog


async def ensure_leaders_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> discord.TextChannel | None:
    """Create or sync the Leaders category and leaders channel for client roles."""
    leaders, _changelog = await ensure_leaders_channels(
        guild,
        bot_member,
        context,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        reason="The Network guild init",
    )
    return leaders


async def grant_leaders_channel_access(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    client_role: discord.Role,
    *,
    access_role_name: str,
) -> None:
    """Add a newly approved client role to the Leaders category and channel."""
    from bot.services.network_provision import resolve_access_role

    access_role = resolve_access_role(guild, role_name=access_role_name)
    if access_role is None:
        return

    from bot.services.guild_layout import resolve_human_moderator_role

    human_moderator_role = resolve_human_moderator_role(guild)

    _category, channel, _changelog = await _sync_leaders_permissions(
        guild,
        bot_member,
        context,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        extra_client_role=client_role,
        reason="The Network client approved",
    )
    if channel is None:
        logger.warning(
            "Could not grant leaders access for new client role",
            extra={"role_id": client_role.id},
        )
