from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord

from bot.app.layout import ApplyMode, LayoutContext, apply_layout
from bot.app.layout.managed import (
    compile_hub_teardown_resources,
    hub_category_names,
    preserved_channel_names,
)
from bot.app.recipes.registry import recipe
from bot.app.recipes.runtime import RecipeContext
from bot.constants import (
    DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
    LEGACY_MODERATOR_ROLE_NAME,
)
from bot.core.discord.cleanup import delete_role
from bot.core.discord.step_runner import run_guild_step
from bot.core.networks.roles import (
    resolve_access_role_by_name,
    resolve_operator_role_by_name,
)

logger = logging.getLogger(__name__)


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
    return category.name.casefold() in hub_category_names()


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


@recipe("hub.uninitialize")
async def uninitialize_guild_recipe(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
) -> GuildUninitResult:
    return await uninitialize_guild(
        guild,
        bot_member,
        access_role_name=recipe_context.bot.settings.network_access_role_name,
        operator_role_name=recipe_context.bot.settings.network_operator_role_name,
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

    access_role = resolve_access_role_by_name(guild, role_name=access_role_name)
    operator_role = resolve_operator_role_by_name(guild, role_name=operator_role_name)
    layout_ctx = LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access_role,
        operator_role=operator_role,
        reason="The Network guild uninit",
    )
    batch = await apply_layout(
        layout_ctx,
        compile_hub_teardown_resources(layout_ctx),
        mode=ApplyMode.TEARDOWN_HUB,
    )
    for item in batch.results:
        if not item.success and item.detail:
            result.failed_steps.append(f"{item.resource_id}: {item.detail}")
            continue
        if not item.changed:
            continue
        if item.resource_id.startswith("detach:"):
            name = item.resource_id.removeprefix("detach:")
            result.preserved_channels.append(f"#{name}")
            result.notes.append(
                f"Moved preserved #{name} out of its category so hub categories can be removed."
            )
        elif item.resource_id.startswith("delete_cat:"):
            result.deleted_categories.append(item.resource_id.removeprefix("delete_cat:"))
        elif item.resource_id.startswith("delete:"):
            result.deleted_channels.append(f"#{item.resource_id.removeprefix('delete:')}")

    roles = [
        role
        for role in guild.roles
        if is_deletable_hub_role(
            role,
            access_role_name=access_role_name,
            operator_role_name=operator_role_name,
        )
    ]
    if perms.manage_roles:
        for role in sorted(roles, key=lambda item: item.position):

            async def _delete_role_step(target: discord.Role = role) -> bool:
                return await delete_role(guild, target.id, label="guild uninit role")

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

    if not result.deleted_channels and not result.deleted_categories and not result.deleted_roles:
        result.notes.append("No hub channels, categories, or roles matched the uninit targets.")

    if result.failed_steps:
        result.notes.insert(
            0,
            f"Uninit completed with {len(result.failed_steps)} warning(s). See notes below.",
        )

    return result
