from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from tests.live.constants import TEST_CLEANUP_REASON

if TYPE_CHECKING:
    from bot.core.runtime import BotContext

logger = logging.getLogger(__name__)

CLEANUP_REASON = TEST_CLEANUP_REASON

PROBE_PREFIX = "network-perm-probe"
DIAG_PREFIX = "diag"
SMOKE_WEBHOOK_PREFIX = "smoke-wh"
SMOKE_CLIENT_CATEGORY_PREFIX = "Smoke Accept "
SMOKE_REBUILD_CATEGORY_PREFIX = "Smoke Rebuild "
SMOKE_CLIENT_SERVER_PREFIXES = (
    "Smoke Accept ",
    "Smoke Deny ",
    "Smoke Rebuild ",
    "Smoke HubSub ",
    "Smoke Welcome ",
)
# Join-approval smoke only during init probes — hub rebuild is cleaned explicitly at test end.
SMOKE_CLIENT_ROLE_PREFIXES = (
    "Client: Smoke Accept ",
    "Client: Smoke Deny ",
    "Client: Smoke Rebuild ",
    "Client: Smoke HubSub ",
    "Client: Smoke Welcome ",
)
SMOKE_REBUILD_ROLE_PREFIX = "Client: Smoke Rebuild "
SMOKE_EMOJI_PREFIX = "tnprobe"
SMOKE_CATEGORY_NAME_PREFIXES = (
    SMOKE_CLIENT_CATEGORY_PREFIX,
    SMOKE_REBUILD_CATEGORY_PREFIX,
    "Smoke Deny ",
    "Smoke HubSub ",
    "Smoke Welcome ",
)

_DIAG_NAME = re.compile(r"^diag", re.IGNORECASE)


def is_smoke_client_server_name(server_name: str) -> bool:
    return server_name.startswith(SMOKE_CLIENT_SERVER_PREFIXES)


def is_test_channel_name(name: str) -> bool:
    lowered = name.casefold()
    return (
        lowered.startswith(PROBE_PREFIX)
        or _DIAG_NAME.match(name) is not None
        or lowered.startswith(SMOKE_WEBHOOK_PREFIX)
    )


def is_test_category_name(name: str) -> bool:
    lowered = name.casefold()
    return any(name.startswith(prefix) for prefix in SMOKE_CATEGORY_NAME_PREFIXES) or (
        lowered.startswith(PROBE_PREFIX) or _DIAG_NAME.match(name) is not None
    )


def is_test_role_name(name: str) -> bool:
    lowered = name.casefold()
    return (
        lowered.startswith(PROBE_PREFIX)
        or _DIAG_NAME.match(name) is not None
        or any(name.startswith(prefix) for prefix in SMOKE_CLIENT_ROLE_PREFIXES)
    )


def is_test_emoji_name(name: str) -> bool:
    return name.startswith(SMOKE_EMOJI_PREFIX)


@dataclass
class GuildTestResourceGuard:
    """RAII guard — tracks Discord resources created during a smoke/probe run."""

    guild: discord.Guild
    bot_member: discord.Member | None = None
    completed_steps: list[str] = field(default_factory=list)
    _webhooks: list[discord.Webhook] = field(default_factory=list)
    _emojis: list[discord.Emoji] = field(default_factory=list)
    _channels: list[discord.abc.GuildChannel] = field(default_factory=list)
    _categories: list[discord.CategoryChannel] = field(default_factory=list)
    _roles: list[discord.Role] = field(default_factory=list)
    _assigned_roles: list[discord.Role] = field(default_factory=list)

    async def __aenter__(self) -> GuildTestResourceGuard:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.cleanup()

    def track_webhook(self, webhook: discord.Webhook) -> discord.Webhook:
        self._webhooks.append(webhook)
        return webhook

    def track_emoji(self, emoji: discord.Emoji) -> discord.Emoji:
        self._emojis.append(emoji)
        return emoji

    def track_channel(self, channel: discord.abc.GuildChannel) -> discord.abc.GuildChannel:
        self._channels.append(channel)
        return channel

    def track_category(self, category: discord.CategoryChannel) -> discord.CategoryChannel:
        self._categories.append(category)
        return category

    def track_role(self, role: discord.Role) -> discord.Role:
        self._roles.append(role)
        return role

    def track_role_assignment(self, role: discord.Role) -> None:
        if role not in self._assigned_roles:
            self._assigned_roles.append(role)

    def record_step(self, label: str) -> None:
        self.completed_steps.append(label)

    async def cleanup(self) -> None:
        if self.bot_member is not None:
            for role in self._assigned_roles:
                if role in self.bot_member.roles:
                    try:
                        await self.bot_member.remove_roles(role, reason=CLEANUP_REASON)
                    except discord.HTTPException:
                        logger.warning(
                            "Test cleanup: could not remove role from member",
                            extra={"role": role.name},
                        )
            self._assigned_roles.clear()

        for webhook in self._webhooks:
            try:
                await webhook.delete(reason=CLEANUP_REASON)
            except discord.HTTPException:
                logger.warning("Test cleanup: could not delete webhook")
        self._webhooks.clear()

        for emoji in self._emojis:
            try:
                await emoji.delete(reason=CLEANUP_REASON)
            except discord.HTTPException:
                logger.warning(
                    "Test cleanup: could not delete emoji",
                    extra={"emoji": emoji.name},
                )
        self._emojis.clear()

        for channel in self._channels:
            await _delete_channel(channel)
        self._channels.clear()

        for category in self._categories:
            await _delete_category(category)
        self._categories.clear()

        for role in self._roles:
            await _delete_role(role)
        self._roles.clear()


@asynccontextmanager
async def guild_test_resource_guard(
    guild: discord.Guild,
    *,
    bot_member: discord.Member | None = None,
) -> AsyncIterator[GuildTestResourceGuard]:
    """RAII scope for live smoke/probe runs."""
    guard = GuildTestResourceGuard(guild, bot_member=bot_member)
    try:
        yield guard
    finally:
        await guard.cleanup()


async def cleanup_guild_test_artifacts(guild: discord.Guild) -> list[str]:
    """Delete leftover probe, diag, and smoke resources from the guild."""
    removed: list[str] = []

    for emoji in list(guild.emojis):
        if not is_test_emoji_name(emoji.name):
            continue
        try:
            await emoji.delete(reason=CLEANUP_REASON)
            removed.append(f"emoji:{emoji.name}")
        except discord.HTTPException:
            logger.warning(
                "Could not delete stale test emoji",
                extra={"emoji": emoji.name},
            )

    for role in list(guild.roles):
        if not is_test_role_name(role.name):
            continue
        try:
            await role.delete(reason=CLEANUP_REASON)
            removed.append(f"role:{role.name}")
        except discord.HTTPException:
            logger.warning(
                "Could not delete stale test role",
                extra={"role": role.name},
            )

    categories = [ch for ch in guild.channels if isinstance(ch, discord.CategoryChannel)]
    for category in categories:
        if not is_test_category_name(category.name):
            continue
        for channel in list(category.channels):
            name = getattr(channel, "name", "")
            try:
                await channel.delete(reason=CLEANUP_REASON)
                removed.append(f"channel:{name}")
            except discord.HTTPException:
                logger.warning(
                    "Could not delete stale test channel in category",
                    extra={"channel": name, "category": category.name},
                )
        try:
            await category.delete(reason=CLEANUP_REASON)
            removed.append(f"category:{category.name}")
        except discord.HTTPException:
            logger.warning(
                "Could not delete stale test category",
                extra={"category": category.name},
            )

    for channel in list(guild.channels):
        if isinstance(channel, discord.CategoryChannel):
            continue
        name = getattr(channel, "name", "")
        if not is_test_channel_name(name):
            continue
        try:
            await channel.delete(reason=CLEANUP_REASON)
            removed.append(f"channel:{name}")
        except discord.HTTPException:
            logger.warning(
                "Could not delete stale test channel",
                extra={"channel": name},
            )

    if removed:
        logger.info("Removed stale guild test artifacts", extra={"removed": removed})
    return removed


async def cleanup_hub_rebuild_smoke_artifacts(
    guild: discord.Guild,
    bot_member: discord.Member | None = None,
) -> list[str]:
    """Delete leftover hub-rebuild smoke clients (call only after rebuild smoke finishes)."""
    removed: list[str] = []

    for role in list(guild.roles):
        if not role.name.startswith(SMOKE_REBUILD_ROLE_PREFIX):
            continue
        try:
            await role.delete(reason=CLEANUP_REASON)
            removed.append(f"role:{role.name}")
        except discord.HTTPException:
            logger.warning(
                "Could not delete stale hub-rebuild smoke role",
                extra={"role": role.name},
            )

    categories = [ch for ch in guild.channels if isinstance(ch, discord.CategoryChannel)]
    for category in categories:
        if not category.name.startswith(SMOKE_REBUILD_CATEGORY_PREFIX):
            continue
        for channel in list(category.channels):
            name = getattr(channel, "name", "")
            await _delete_channel(channel, bot_member=bot_member)
            removed.append(f"channel:{name}")
        if category.channels:
            logger.warning(
                "Hub-rebuild cleanup: smoke category still has channels; skipping category delete",
                extra={"category": category.name, "remaining": len(category.channels)},
            )
            continue
        try:
            await category.delete(reason=CLEANUP_REASON)
            removed.append(f"category:{category.name}")
        except discord.HTTPException:
            logger.warning(
                "Could not delete stale hub-rebuild smoke category",
                extra={"category": category.name},
            )

    if removed:
        logger.info(
            "Removed stale hub-rebuild smoke artifacts",
            extra={"removed": removed},
        )
    return removed


async def cleanup_orphan_smoke_subscription_channels(
    guild: discord.Guild,
    context: BotContext,
) -> list[str]:
    """Remove uncategorized publish/subscribe channels not owned by any live client.

    Returns channel names the bot could not delete (requires manual removal in Discord).
    """
    referenced: set[int] = set()
    for client in await context.store.clients.list_all():
        referenced.add(client.profile_channel_id)
        for subscription in await context.store.clients.list_subscriptions_by_client(client.id):
            referenced.add(subscription.publish_channel_id)
            referenced.add(subscription.subscribe_channel_id)

    manual: list[str] = []
    for channel in list(guild.channels):
        if isinstance(channel, discord.CategoryChannel):
            continue
        if channel.category is not None:
            continue
        name = getattr(channel, "name", "")
        if not name.casefold().startswith("smoke-"):
            continue
        if not (name.endswith("-publish") or name.endswith("-subscribe")):
            continue
        if channel.id in referenced:
            continue
        try:
            await channel.delete(reason=CLEANUP_REASON)
        except discord.HTTPException:
            manual.append(f"#{name} ({channel.id})")

    if manual:
        logger.warning(
            "Could not delete orphan smoke subscription channels; remove manually in Discord",
            extra={"channels": manual},
        )
    return manual


async def cleanup_stale_probe_resources(guild: discord.Guild) -> list[str]:
    return await cleanup_guild_test_artifacts(guild)


async def delete_guild_channel_for_cleanup(
    channel: discord.abc.GuildChannel,
    *,
    reason: str,
    bot_member: discord.Member | None = None,
    delete_webhooks: bool = False,
) -> None:
    """Delete a guild channel, optionally clearing webhooks and syncing category perms."""
    if (
        bot_member is not None
        and channel.category is not None
        and not channel.permissions_for(bot_member).manage_channels
    ):
        try:
            await channel.edit(sync_permissions=True, reason=reason)  # type: ignore[attr-defined]
        except discord.HTTPException:
            pass

    if delete_webhooks and isinstance(channel, discord.TextChannel) and not channel.is_news():
        try:
            webhooks = await channel.webhooks()
        except discord.HTTPException:
            webhooks = []
        for webhook in webhooks:
            try:
                await webhook.delete(reason=reason)
            except discord.HTTPException:
                logger.warning(
                    "Test cleanup: could not delete webhook",
                    extra={"channel_id": channel.id, "webhook_id": webhook.id},
                )

    name = getattr(channel, "name", str(channel.id))
    try:
        await channel.delete(reason=reason)
    except discord.NotFound:
        return
    except discord.HTTPException:
        logger.warning("Test cleanup: could not delete channel", extra={"channel": name})


async def _delete_channel(
    channel: discord.abc.GuildChannel,
    *,
    bot_member: discord.Member | None = None,
) -> None:
    await delete_guild_channel_for_cleanup(
        channel,
        reason=CLEANUP_REASON,
        bot_member=bot_member,
    )


async def _delete_category(category: discord.CategoryChannel) -> None:
    for channel in list(category.channels):
        await _delete_channel(channel)
    try:
        await category.delete(reason=CLEANUP_REASON)
    except discord.HTTPException:
        logger.warning(
            "Test cleanup: could not delete category",
            extra={"category": category.name},
        )


async def _delete_role(role: discord.Role) -> None:
    try:
        await role.delete(reason=CLEANUP_REASON)
    except discord.HTTPException:
        logger.warning("Test cleanup: could not delete role", extra={"role": role.name})
