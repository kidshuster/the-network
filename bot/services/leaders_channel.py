from __future__ import annotations

import logging
from dataclasses import dataclass, field
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
    sync_channel_permission_overwrites,
)

if TYPE_CHECKING:
    from bot.context import BotContext

logger = logging.getLogger(__name__)

LEADERS_CHANNEL_SETTINGS_KEY = "hub_leaders_channel"
CHANGELOG_CHANNEL_SETTINGS_KEY = "hub_changelog_channel"


@dataclass
class LeadersSyncResult:
    roles_synced: list[str] = field(default_factory=list)
    roles_missing: list[str] = field(default_factory=list)
    leaders_channel: discord.TextChannel | None = None
    changelog_channel: discord.TextChannel | None = None
    failures: list[str] = field(default_factory=list)

    def rectification_notes(self) -> list[str]:
        notes: list[str] = []
        if self.roles_synced:
            role_list = ", ".join(self.roles_synced)
            targets: list[str] = ["Leaders category"]
            if self.leaders_channel is not None:
                targets.append(self.leaders_channel.mention)
            if self.changelog_channel is not None:
                targets.append(self.changelog_channel.mention)
            notes.append(
                f"Leaders access synced for **{len(self.roles_synced)}** client role(s) "
                f"({role_list}) on {', '.join(targets)}."
            )
        elif not self.roles_missing and not self.failures:
            notes.append("Leaders channels verified — no client roles registered yet.")
        return notes

    def skip_notes(self) -> list[str]:
        return [
            f"Leaders: skipped **{server_name}** — client role missing in Discord."
            for server_name in self.roles_missing
        ]


async def _list_client_roles(
    guild: discord.Guild,
    context: BotContext,
    *,
    extra_role: discord.Role | None = None,
) -> tuple[list[discord.Role], list[str]]:
    client_roles: list[discord.Role] = []
    missing_clients: list[str] = []
    for client in await context.client_repo.list_all():
        if client.guild_id != guild.id:
            continue
        role = guild.get_role(client.client_role_id)
        if role is not None:
            client_roles.append(role)
        else:
            missing_clients.append(client.server_name)
    if extra_role is not None and extra_role not in client_roles:
        client_roles.append(extra_role)
    return client_roles, missing_clients


async def _resolve_stored_text_channel(
    guild: discord.Guild,
    context: BotContext,
    settings_key: str,
) -> discord.TextChannel | None:
    raw = await context.settings_repo.get(settings_key)
    if raw is None:
        return None
    try:
        channel_id = int(raw)
    except ValueError:
        return None
    channel = guild.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


async def _resolve_leaders_channel_for_sync(
    guild: discord.Guild,
    context: BotContext,
) -> discord.TextChannel | None:
    stored = await _resolve_stored_text_channel(
        guild,
        context,
        LEADERS_CHANNEL_SETTINGS_KEY,
    )
    if stored is not None:
        return stored
    return resolve_leaders_channel(guild)


async def _resolve_changelog_channel_for_sync(
    guild: discord.Guild,
    context: BotContext,
) -> discord.TextChannel | None:
    stored = await _resolve_stored_text_channel(
        guild,
        context,
        CHANGELOG_CHANNEL_SETTINGS_KEY,
    )
    if stored is not None:
        return stored
    return resolve_changelog_channel(guild)


async def _ensure_leaders_text_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    channel: discord.TextChannel | None,
    category: discord.CategoryChannel,
    name: str,
    overwrites: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
    topic: str,
    reason: str,
    sync_result: LeadersSyncResult,
) -> discord.TextChannel | None:
    from bot.services.guild_permissions import create_text_channel_with_overwrites

    if channel is None:
        try:
            return await create_text_channel_with_overwrites(
                guild,
                bot_member,
                name=name,
                category=category,
                overwrites=overwrites,
                topic=topic,
                reason=reason,
            )
        except discord.HTTPException as exc:
            sync_result.failures.append(f"Leaders: could not create #{name} ({exc}).")
            return None

    move_kwargs: dict[str, object] = {}
    if channel.category_id != category.id or channel.name != name:
        move_kwargs["category"] = category
        move_kwargs["name"] = name

    try:
        await sync_channel_permission_overwrites(
            channel,
            bot_member,
            overwrites,
            reason=reason,
            **move_kwargs,
        )
    except discord.HTTPException as exc:
        sync_result.failures.append(
            f"Leaders: could not sync {channel.mention} permissions ({exc})."
        )
    return channel


async def _sync_leaders_permissions(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    operator_role: discord.Role | None,
    extra_client_role: discord.Role | None = None,
    reason: str,
) -> tuple[
    discord.CategoryChannel | None,
    discord.TextChannel | None,
    discord.TextChannel | None,
    LeadersSyncResult,
]:
    sync_result = LeadersSyncResult()
    client_roles, missing_clients = await _list_client_roles(
        guild,
        context,
        extra_role=extra_client_role,
    )
    sync_result.roles_missing = missing_clients
    sync_result.roles_synced = [role.name for role in client_roles]

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
            operator_role=operator_role,
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
            operator_role=operator_role,
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
        except discord.HTTPException as exc:
            logger.warning("Could not create Leaders category")
            sync_result.failures.append(f"Leaders: could not create category ({exc}).")
            return None, None, None, sync_result
    else:
        try:
            await category.edit(overwrites=category_overwrites, reason=reason)
        except discord.HTTPException as exc:
            logger.warning(
                "Could not sync Leaders category permissions",
                extra={"category_id": category.id},
            )
            sync_result.failures.append(
                f"Leaders: could not sync category permissions ({exc})."
            )

    channel = await _ensure_leaders_text_channel(
        guild,
        bot_member,
        channel=await _resolve_leaders_channel_for_sync(guild, context),
        category=category,
        name=CHANNEL_LEADERS,
        overwrites=dict(channel_overwrites),
        topic="Private channel for participating server leaders",
        reason=reason,
        sync_result=sync_result,
    )
    sync_result.leaders_channel = channel

    changelog = await _ensure_leaders_text_channel(
        guild,
        bot_member,
        channel=await _resolve_changelog_channel_for_sync(guild, context),
        category=category,
        name=CHANNEL_CHANGELOG,
        overwrites=dict(changelog_overwrites),
        topic="Release notes for The Network bot",
        reason=reason,
        sync_result=sync_result,
    )
    sync_result.changelog_channel = changelog

    return category, channel, changelog, sync_result


async def ensure_leaders_channels(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    operator_role: discord.Role | None = None,
    reason: str = "The Network guild init",
) -> tuple[discord.TextChannel | None, discord.TextChannel | None, LeadersSyncResult]:
    """Create or sync Leaders category channels for client roles."""
    _category, leaders, changelog, sync_result = await _sync_leaders_permissions(
        guild,
        bot_member,
        context,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        operator_role=operator_role,
        reason=reason,
    )
    if leaders is not None:
        await context.settings_repo.set(LEADERS_CHANNEL_SETTINGS_KEY, str(leaders.id))
    if changelog is not None:
        await context.settings_repo.set(CHANGELOG_CHANNEL_SETTINGS_KEY, str(changelog.id))
    return leaders, changelog, sync_result


async def ensure_leaders_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> discord.TextChannel | None:
    """Create or sync the Leaders category and leaders channel for client roles."""
    leaders, _changelog, _sync_result = await ensure_leaders_channels(
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
    operator_role_name: str,
) -> None:
    """Add a newly approved client role to the Leaders category and channel."""
    from bot.services.network_provision import (
        resolve_access_role,
        resolve_operator_role_by_name,
    )

    access_role = resolve_access_role(guild, role_name=access_role_name)
    if access_role is None:
        return

    from bot.services.guild_layout import resolve_human_moderator_role

    human_moderator_role = resolve_human_moderator_role(guild)
    operator_role = resolve_operator_role_by_name(guild, role_name=operator_role_name)

    _category, channel, _changelog, sync_result = await _sync_leaders_permissions(
        guild,
        bot_member,
        context,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        operator_role=operator_role,
        extra_client_role=client_role,
        reason="The Network client approved",
    )
    if channel is None:
        logger.warning(
            "Could not grant leaders access for new client role",
            extra={"role_id": client_role.id},
        )
    elif sync_result.failures:
        logger.warning(
            "Leaders access partially failed for new client role",
            extra={"role_id": client_role.id, "failures": sync_result.failures},
        )
