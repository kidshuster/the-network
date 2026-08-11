from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord

from bot.constants import (
    DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    LEGACY_MODERATOR_ROLE_NAME,
)
from bot.core.discord.cleanup import delete_channel, delete_role
from bot.core.discord.step_runner import run_guild_step
from bot.core.hub.resolve import (
    CATEGORY_SUBSCRIBE,
    CHANNEL_WELCOME_SINK,
)
from bot.core.layout.managed import hub_category_names, preserved_channel_names

logger = logging.getLogger(__name__)

# Legacy subscribe category still cleaned up on uninit.
_LEGACY_HUB_CATEGORY_NAMES = frozenset({CATEGORY_SUBSCRIBE.casefold()})


@dataclass
class GuildUninitResult:
    success: bool
    deleted_channels: list[str] = field(default_factory=list)
    deleted_categories: list[str] = field(default_factory=list)
    deleted_roles: list[str] = field(default_factory=list)
    preserved_channels: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reason: str | None = None


def _channel_label(channel: discord.abc.GuildChannel) -> str:
    return f"#{channel.name}" if hasattr(channel, "name") else str(channel.id)


def is_preserved_hub_channel(
    guild: discord.Guild,
    channel: discord.abc.GuildChannel,
) -> bool:
    rules = guild.rules_channel
    if isinstance(rules, discord.TextChannel) and channel.id == rules.id:
        return True
    name = getattr(channel, "name", None)
    if name is not None and name.casefold() in preserved_channel_names():
        return True
    return False


def is_hub_managed_category(category: discord.CategoryChannel) -> bool:
    name = category.name.casefold()
    if name in hub_category_names() or name in _LEGACY_HUB_CATEGORY_NAMES:
        return True
    return name.endswith(" feed")


def is_deletable_hub_role(
    role: discord.Role,
    *,
    access_role_name: str,
    operator_role_name: str,
) -> bool:
    if role.is_default():
        return False
    if role.managed:
        return False
    if role.name.casefold() == access_role_name.casefold():
        return False
    if role.name.casefold() == operator_role_name.casefold():
        return False
    if role.name == DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME:
        return True
    if role.name == LEGACY_MODERATOR_ROLE_NAME:
        return True
    return False


def collect_uninit_targets(
    guild: discord.Guild,
    *,
    access_role_name: str = DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    operator_role_name: str = DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
) -> tuple[
    list[discord.abc.GuildChannel],
    list[discord.CategoryChannel],
    list[discord.Role],
    list[discord.abc.GuildChannel],
]:
    preserved: list[discord.abc.GuildChannel] = []
    channels_to_delete: list[discord.abc.GuildChannel] = []
    categories_to_delete: list[discord.CategoryChannel] = []

    for category in guild.categories:
        if is_hub_managed_category(category):
            categories_to_delete.append(category)

    category_ids_to_delete = {category.id for category in categories_to_delete}

    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        if is_preserved_hub_channel(guild, channel):
            preserved.append(channel)
            continue
        category_id = getattr(channel, "category_id", None)
        if category_id in category_ids_to_delete:
            channels_to_delete.append(channel)
            continue
        name = getattr(channel, "name", "").casefold()
        if name == CHANNEL_WELCOME_SINK:
            channels_to_delete.append(channel)
            continue
        if name.startswith("join-"):
            channels_to_delete.append(channel)
        if name == "join-the-network" and category_id in category_ids_to_delete:
            pass  # handled via category delete

    roles_to_delete = [
        role
        for role in guild.roles
        if is_deletable_hub_role(
            role,
            access_role_name=access_role_name,
            operator_role_name=operator_role_name,
        )
    ]

    return channels_to_delete, categories_to_delete, roles_to_delete, preserved


async def _run_uninit_step[T](
    result: GuildUninitResult,
    step: str,
    action: Callable[[], Awaitable[T]],
) -> T | None:
    return await run_guild_step(result, step, action)


async def _detach_preserved_channels(
    preserved: list[discord.abc.GuildChannel],
    *,
    result: GuildUninitResult,
) -> None:
    for channel in preserved:
        if not isinstance(channel, discord.TextChannel):
            continue
        if channel.category_id is None:
            continue

        async def _detach(ch: discord.TextChannel = channel) -> bool:
            await ch.edit(category=None, reason="The Network guild uninit")
            return True

        if await _run_uninit_step(
            result,
            f"move preserved {_channel_label(channel)} out of its category",
            _detach,
        ):
            result.notes.append(
                f"Moved preserved {_channel_label(channel)} out of its category "
                "so hub categories can be removed."
            )


async def uninitialize_guild(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    access_role_name: str = DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    operator_role_name: str = DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
) -> GuildUninitResult:
    result = GuildUninitResult(success=True)
    perms = bot_member.guild_permissions
    if not perms.manage_channels:
        return GuildUninitResult(
            success=False,
            reason="The bot needs **Manage Channels** to remove hub channels and categories.",
        )

    channels, categories, roles, preserved = collect_uninit_targets(
        guild,
        access_role_name=access_role_name,
        operator_role_name=operator_role_name,
    )

    for channel in preserved:
        result.preserved_channels.append(_channel_label(channel))

    await _detach_preserved_channels(preserved, result=result)

    seen_channel_ids: set[int] = set()
    for channel in sorted(channels, key=lambda ch: ch.id):
        if channel.id in seen_channel_ids:
            continue
        seen_channel_ids.add(channel.id)
        async def _delete_step(ch: discord.abc.GuildChannel = channel) -> bool:
            return await delete_channel(guild, ch.id, label="guild uninit")

        deleted = await _run_uninit_step(
            result,
            f"delete {_channel_label(channel)}",
            _delete_step,
        )
        if deleted:
            result.deleted_channels.append(_channel_label(channel))

    seen_category_ids: set[int] = set()
    for category in sorted(categories, key=lambda cat: cat.id):
        if category.id in seen_category_ids:
            continue
        seen_category_ids.add(category.id)
        async def _delete_category_step(
            cat: discord.CategoryChannel = category,
        ) -> bool:
            return await delete_channel(guild, cat.id, label="guild uninit category")

        deleted = await _run_uninit_step(
            result,
            f"delete category {category.name}",
            _delete_category_step,
        )
        if deleted:
            result.deleted_categories.append(category.name)

    if perms.manage_roles:
        for role in sorted(roles, key=lambda r: r.position):
            async def _delete_role_step(r: discord.Role = role) -> bool:
                return await delete_role(guild, r.id, label="guild uninit role")

            deleted = await _run_uninit_step(
                result,
                f"delete role {role.name}",
                _delete_role_step,
            )
            if deleted:
                result.deleted_roles.append(role.name)
    elif roles:
        result.notes.append(
            "Skipped role cleanup — the bot needs **Manage Roles** to delete "
            "**Moderator** and **Partner:** roles."
        )

    if (
        not result.deleted_channels
        and not result.deleted_categories
        and not result.deleted_roles
    ):
        result.notes.append("No hub channels, categories, or roles matched the uninit targets.")

    if result.failed_steps:
        result.notes.insert(
            0,
            f"Uninit completed with {len(result.failed_steps)} warning(s). See notes below.",
        )

    return result
