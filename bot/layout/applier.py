from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

import discord

from bot.layout.compiler import DesiredResource, ResourceKind
from bot.layout.roles import LayoutContext
from bot.permissions.service import (
    PermissionContext,
    build_context,
    permission_service,
)

logger = logging.getLogger(__name__)


class ApplyMode(Enum):
    ENSURE = "ensure"
    RECONCILE_ONLY = "reconcile_only"
    TEARDOWN_HUB = "teardown_hub"


@dataclass
class ResourceApplyResult:
    resource_id: str
    success: bool
    changed: bool = False
    detail: str | None = None
    channel: discord.abc.GuildChannel | None = None


@dataclass
class BatchApplyResult:
    results: list[ResourceApplyResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return all(item.success for item in self.results)

    @property
    def failures(self) -> list[str]:
        return [
            f"{item.resource_id}: {item.detail}"
            for item in self.results
            if not item.success and item.detail
        ]

    def resource(self, resource_id: str) -> discord.abc.GuildChannel | None:
        for item in self.results:
            if item.resource_id == resource_id and item.channel is not None:
                return item.channel
        return None


def _permission_context(context: LayoutContext) -> PermissionContext:
    return build_context(
        context.guild,
        context.bot_member,
        access_role=context.access_role,
        moderator_role=context.moderator_role,
        operator_role=context.operator_role,
    )


def _find_category(
    guild: discord.Guild,
    resource: DesiredResource,
) -> discord.CategoryChannel | None:
    target = resource.name.casefold()
    for category in guild.categories:
        if category.name.casefold() == target:
            return category
    return None


def _find_text_channel(
    guild: discord.Guild,
    resource: DesiredResource,
    *,
    category: discord.CategoryChannel | None,
) -> discord.TextChannel | None:
    names = {resource.name.casefold(), *(n.casefold() for n in resource.legacy_names)}
    if resource.community_slot == "rules":
        rules = guild.rules_channel
        if isinstance(rules, discord.TextChannel):
            return rules

    # Prefer in-category match
    if category is not None:
        for channel in guild.text_channels:
            if channel.category_id == category.id and channel.name.casefold() in names:
                return channel

    for channel in guild.text_channels:
        if channel.name.casefold() in names:
            return channel
    return None


async def _ensure_category(
    context: LayoutContext,
    resource: DesiredResource,
) -> ResourceApplyResult:
    perm = _permission_context(context)
    existing = _find_category(context.guild, resource)
    try:
        result = await permission_service.ensure_category(
            context.guild,
            perm,
            existing=existing,
            name=resource.name,
            overwrites=resource.overwrites,
            reason=context.reason,
        )
    except discord.HTTPException as exc:
        return ResourceApplyResult(
            resource_id=resource.id,
            success=False,
            detail=str(exc),
        )
    return ResourceApplyResult(
        resource_id=resource.id,
        success=result.sync.success,
        changed=result.sync.changed,
        detail="; ".join(result.sync.failures) or None,
        channel=result.resource,
    )


async def _ensure_channel(
    context: LayoutContext,
    resource: DesiredResource,
    categories: dict[str, discord.CategoryChannel],
    *,
    reconcile_only: bool,
) -> ResourceApplyResult:
    perm = _permission_context(context)
    category = categories.get(resource.category_ref or "")
    existing = _find_text_channel(context.guild, resource, category=category)

    if reconcile_only and existing is None:
        return ResourceApplyResult(
            resource_id=resource.id,
            success=False,
            detail="channel missing",
        )

    if existing is not None:
        try:
            edits: dict[str, object] = {}
            if category is not None and existing.category_id != category.id:
                edits["category"] = category
            if existing.name != resource.name:
                edits["name"] = resource.name
            if resource.topic is not None and getattr(existing, "topic", None) != resource.topic:
                edits["topic"] = resource.topic
            if edits:
                await existing.edit(reason=context.reason, **edits)  # type: ignore[call-overload]

            if resource.inherit and category is not None:
                sync = await permission_service.reconcile_map(
                    existing,
                    perm,
                    resource.overwrites,
                    reason=context.reason,
                    inherit=True,
                )
            else:
                sync = await permission_service.reconcile_map(
                    existing,
                    perm,
                    resource.overwrites,
                    reason=context.reason,
                )
            return ResourceApplyResult(
                resource_id=resource.id,
                success=sync.success,
                changed=sync.changed or bool(edits),
                detail="; ".join(sync.failures) or None,
                channel=existing,
            )
        except discord.HTTPException as exc:
            return ResourceApplyResult(
                resource_id=resource.id,
                success=False,
                detail=str(exc),
                channel=existing,
            )

    # Community slots: never delete/recreate; create only if missing
    try:
        result = await permission_service.ensure_text_channel(
            context.guild,
            perm,
            existing=None,
            name=resource.name,
            category=category,
            overwrites=resource.overwrites,
            topic=resource.topic,
            news=resource.kind is ResourceKind.ANNOUNCEMENT,
            reason=context.reason,
        )
        if resource.inherit and category is not None:
            await permission_service.reconcile_map(
                result.resource,
                perm,
                resource.overwrites,
                reason=context.reason,
                inherit=True,
            )
        if resource.community_slot == "rules":
            try:
                await context.guild.edit(rules_channel=result.resource, reason=context.reason)
            except discord.HTTPException:
                logger.warning("Could not bind guild rules_channel", exc_info=True)
        return ResourceApplyResult(
            resource_id=resource.id,
            success=result.sync.success,
            changed=True,
            detail="; ".join(result.sync.failures) or None,
            channel=result.resource,
        )
    except discord.HTTPException as exc:
        return ResourceApplyResult(
            resource_id=resource.id,
            success=False,
            detail=str(exc),
        )


async def _teardown_hub(
    context: LayoutContext,
    resources: list[DesiredResource],
) -> BatchApplyResult:
    from bot.discord_util.cleanup import delete_channel

    batch = BatchApplyResult()
    hub_category_names = {
        r.name.casefold()
        for r in resources
        if r.kind is ResourceKind.CATEGORY and r.managed == "hub"
    }
    preserve_names = {
        r.name.casefold()
        for r in resources
        if r.preserve_on_uninit or r.community_slot is not None
    }
    for resource in resources:
        preserve_names.update(n.casefold() for n in resource.legacy_names)

    # Detach preserved/community channels from hub categories
    for channel in list(context.guild.text_channels):
        category = channel.category
        if category is None or category.name.casefold() not in hub_category_names:
            continue
        is_rules = (
            isinstance(context.guild.rules_channel, discord.TextChannel)
            and channel.id == context.guild.rules_channel.id
        )
        if is_rules or channel.name.casefold() in preserve_names:
            try:
                await channel.edit(category=None, reason=context.reason)
                batch.results.append(
                    ResourceApplyResult(
                        resource_id=f"detach:{channel.name}",
                        success=True,
                        changed=True,
                        channel=channel,
                    )
                )
            except discord.HTTPException as exc:
                batch.results.append(
                    ResourceApplyResult(
                        resource_id=f"detach:{channel.name}",
                        success=False,
                        detail=str(exc),
                    )
                )

    # Delete non-preserved channels in hub categories
    for channel in list(context.guild.text_channels):
        category = channel.category
        if category is None or category.name.casefold() not in hub_category_names:
            continue
        is_rules = (
            isinstance(context.guild.rules_channel, discord.TextChannel)
            and channel.id == context.guild.rules_channel.id
        )
        if is_rules or channel.name.casefold() in preserve_names:
            continue
        ok = await delete_channel(
            context.guild,
            channel.id,
            label=f"hub teardown #{channel.name}",
        )
        batch.results.append(
            ResourceApplyResult(
                resource_id=f"delete:{channel.name}",
                success=ok,
                changed=ok,
                detail=None if ok else "delete failed",
            )
        )

    # Delete hub categories
    for category in list(context.guild.categories):
        if category.name.casefold() not in hub_category_names:
            continue
        ok = await delete_channel(
            context.guild,
            category.id,
            label=f"hub teardown category {category.name}",
        )
        batch.results.append(
            ResourceApplyResult(
                resource_id=f"delete_cat:{category.name}",
                success=ok,
                changed=ok,
                detail=None if ok else "delete failed",
            )
        )
    return batch


async def apply_layout(
    context: LayoutContext,
    resources: list[DesiredResource],
    *,
    mode: ApplyMode = ApplyMode.ENSURE,
) -> BatchApplyResult:
    if mode is ApplyMode.TEARDOWN_HUB:
        return await _teardown_hub(context, resources)

    batch = BatchApplyResult()
    categories: dict[str, discord.CategoryChannel] = {}
    reconcile_only = mode is ApplyMode.RECONCILE_ONLY

    for resource in resources:
        if resource.kind is ResourceKind.CATEGORY:
            if reconcile_only:
                existing = _find_category(context.guild, resource)
                if existing is None:
                    batch.results.append(
                        ResourceApplyResult(
                            resource_id=resource.id,
                            success=False,
                            detail="category missing",
                        )
                    )
                    continue
                perm = _permission_context(context)
                sync = await permission_service.reconcile_map(
                    existing,
                    perm,
                    resource.overwrites,
                    reason=context.reason,
                )
                batch.results.append(
                    ResourceApplyResult(
                        resource_id=resource.id,
                        success=sync.success,
                        changed=sync.changed,
                        detail="; ".join(sync.failures) or None,
                        channel=existing,
                    )
                )
                categories[resource.id] = existing
                continue

            result = await _ensure_category(context, resource)
            batch.results.append(result)
            if isinstance(result.channel, discord.CategoryChannel):
                categories[resource.id] = result.channel
            continue

        result = await _ensure_channel(
            context,
            resource,
            categories,
            reconcile_only=reconcile_only,
        )
        batch.results.append(result)

    # Position pass for channels with explicit positions
    by_category: dict[str, list[DesiredResource]] = {}
    for resource in resources:
        if resource.kind is ResourceKind.CATEGORY:
            continue
        if resource.position is None or resource.category_ref is None:
            continue
        by_category.setdefault(resource.category_ref, []).append(resource)
    for category_id, ordered in by_category.items():
        category = categories.get(category_id)
        if category is None:
            continue
        for resource in sorted(ordered, key=lambda item: item.position or 0):
            channel = batch.resource(resource.id)
            if not isinstance(channel, discord.TextChannel):
                continue
            if resource.position is None:
                continue
            try:
                await channel.edit(position=resource.position, reason=context.reason)
            except discord.HTTPException:
                logger.debug("Could not set position for #%s", resource.name, exc_info=True)

    return batch
