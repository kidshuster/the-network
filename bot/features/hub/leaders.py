from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from bot.app.layout import ApplyMode, LayoutContext, apply_layout, compile_hub_slice
from bot.features.channels.resolve import (
    CHANNEL_CHANGELOG,
    CHANNEL_LEADERS,
    resolve_changelog_channel,
    resolve_leaders_category,
    resolve_leaders_channel,
)

if TYPE_CHECKING:
    from bot.app.context import BotContext

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
    for client in await context.store.clients.list_all():
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


async def ensure_leaders_channels(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    operator_role: discord.Role | None = None,
    extra_client_role: discord.Role | None = None,
    reason: str = "The Network guild init",
) -> tuple[discord.TextChannel | None, discord.TextChannel | None, LeadersSyncResult]:
    """Create or sync Leaders category channels for client roles."""
    sync_result = LeadersSyncResult()
    client_roles, missing = await _list_client_roles(
        guild,
        context,
        extra_role=extra_client_role,
    )
    sync_result.roles_missing = missing
    sync_result.roles_synced = [role.name for role in client_roles]

    layout_ctx = LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access_role,
        moderator_role=human_moderator_role,
        operator_role=operator_role,
        client_roles=tuple(client_roles),
        reason=reason,
    )
    batch = await apply_layout(
        layout_ctx,
        compile_hub_slice(
            layout_ctx,
            category_ids={"leaders"},
            channel_ids={"leaders_channel", "changelog"},
        ),
        mode=ApplyMode.ENSURE,
    )
    sync_result.failures = [
        f"Leaders: {item.resource_id}: {item.detail}" for item in batch.results if not item.success
    ]

    leaders = batch.resource("leaders_channel")
    changelog = batch.resource("changelog")
    sync_result.leaders_channel = leaders if isinstance(leaders, discord.TextChannel) else None
    sync_result.changelog_channel = (
        changelog if isinstance(changelog, discord.TextChannel) else None
    )

    # Prefer resolved channels if batch missed (e.g. reconcile quirks)
    if sync_result.leaders_channel is None:
        sync_result.leaders_channel = resolve_leaders_channel(guild)
    if sync_result.changelog_channel is None:
        sync_result.changelog_channel = resolve_changelog_channel(guild)
    _ = resolve_leaders_category(guild)

    if sync_result.leaders_channel is not None:
        await context.store.settings.set(
            LEADERS_CHANNEL_SETTINGS_KEY,
            str(sync_result.leaders_channel.id),
        )
    if sync_result.changelog_channel is not None:
        await context.store.settings.set(
            CHANGELOG_CHANNEL_SETTINGS_KEY,
            str(sync_result.changelog_channel.id),
        )
    return sync_result.leaders_channel, sync_result.changelog_channel, sync_result


async def grant_leaders_channel_access(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    client_role: discord.Role,
    *,
    access_role_name: str,
    operator_role_name: str,
) -> LeadersSyncResult:
    from bot.features.channels.resolve import resolve_human_moderator_role
    from bot.features.networks.roles import (
        resolve_access_role,
        resolve_operator_role_by_name,
    )

    _leaders, _changelog, sync_result = await ensure_leaders_channels(
        guild,
        bot_member,
        context,
        access_role=resolve_access_role(guild, role_name=access_role_name),
        human_moderator_role=resolve_human_moderator_role(guild),
        operator_role=resolve_operator_role_by_name(guild, role_name=operator_role_name),
        extra_client_role=client_role,
        reason="The Network client approved",
    )
    if sync_result.failures:
        logger.warning(
            "Leaders access sync reported failures",
            extra={"role_id": client_role.id, "failures": sync_result.failures},
        )
    return sync_result


__all__ = [
    "CHANGELOG_CHANNEL_SETTINGS_KEY",
    "CHANNEL_CHANGELOG",
    "CHANNEL_LEADERS",
    "LEADERS_CHANNEL_SETTINGS_KEY",
    "LeadersSyncResult",
    "ensure_leaders_channels",
    "grant_leaders_channel_access",
]
