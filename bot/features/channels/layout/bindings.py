from __future__ import annotations

import logging

import discord

from bot.core.channels.migration import MigrationBinding, MigrationPlan
from bot.core.discord.cleanup import delete_channel
from bot.features.channels.layout.roles import LayoutContext

logger = logging.getLogger(__name__)


def _resolve_guild_channel(
    guild: discord.Guild,
    discord_id: int,
) -> discord.CategoryChannel | discord.TextChannel | None:
    channel = guild.get_channel(discord_id)
    if isinstance(channel, (discord.CategoryChannel, discord.TextChannel)):
        return channel
    for item in (*guild.categories, *guild.text_channels):
        if item.id == discord_id and isinstance(
            item,
            (discord.CategoryChannel, discord.TextChannel),
        ):
            return item
    return None


async def apply_migration_bindings(
    context: LayoutContext,
    plan: MigrationPlan,
    *,
    category_bound_ids: dict[str, int] | None = None,
) -> list[str]:
    """Rename/move bound channels toward desired names/parents; delete confirmed leftovers."""
    notes: list[str] = []
    category_ids = dict(category_bound_ids or {})
    for binding in plan.bindings:
        if binding.category_key is None:
            # Categories first so channel moves can resolve parents.
            channel = _resolve_guild_channel(context.guild, binding.discord_id)
            if isinstance(channel, discord.CategoryChannel):
                category_ids[binding.resource_key] = channel.id

    # Ensure category bindings are applied before channels.
    ordered = sorted(
        plan.bindings,
        key=lambda item: 0 if item.category_key is None else 1,
    )
    for binding in ordered:
        channel = _resolve_guild_channel(context.guild, binding.discord_id)
        if channel is None:
            notes.append(
                f"Skipped binding `{binding.resource_key}`: Discord id "
                f"{binding.discord_id} missing."
            )
            continue
        changed = await _sync_bound_channel(
            context,
            binding,
            channel,
            category_ids=category_ids,
        )
        if changed:
            notes.append(
                f"Migrated `{binding.resource_key}` "
                f"(#{binding.current_name} → #{binding.target_name})."
            )
            if isinstance(channel, discord.CategoryChannel):
                category_ids[binding.resource_key] = channel.id

    for candidate in plan.delete_candidates:
        deleted = await delete_channel(
            context.guild,
            candidate.discord_id,
            label=f"obsolete hub channel #{candidate.name}",
        )
        if deleted:
            notes.append(f"Removed obsolete `#{candidate.name}`.")
        else:
            notes.append(f"Failed to remove obsolete `#{candidate.name}`.")
    return notes


async def _sync_bound_channel(
    context: LayoutContext,
    binding: MigrationBinding,
    channel: discord.CategoryChannel | discord.TextChannel,
    *,
    category_ids: dict[str, int],
) -> bool:
    kwargs: dict[str, object] = {}
    if channel.name != binding.target_name:
        kwargs["name"] = binding.target_name
    if binding.category_key is not None and isinstance(channel, discord.TextChannel):
        parent_id = category_ids.get(binding.category_key)
        if parent_id is not None and channel.category_id != parent_id:
            parent = _resolve_guild_channel(context.guild, parent_id)
            if isinstance(parent, discord.CategoryChannel):
                kwargs["category"] = parent
    if not kwargs:
        return False
    edit = getattr(channel, "edit", None)
    if edit is None:
        return False
    try:
        result = edit(**kwargs, reason=context.reason)
        if hasattr(result, "__await__"):
            await result
        return True
    except discord.HTTPException:
        logger.warning(
            "Could not migrate bound channel",
            extra={
                "resource_key": binding.resource_key,
                "discord_id": binding.discord_id,
                "changes": sorted(kwargs),
            },
            exc_info=True,
        )
        return False
