from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

import discord

from bot.app.layout.compiler import DesiredResource, ResourceKind
from bot.app.layout.roles import LayoutContext, resolve_targets
from bot.core.channels.finder import find_channel
from bot.core.permissions.service import (
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
    bot_access = resolve_targets(context, "bot_access")
    return build_context(
        context.guild,
        context.bot_member,
        access_role=context.access_role,
        moderator_role=context.moderator_role,
        # PermissionContext.operator_role backs bot_access_role used by validation.
        operator_role=bot_access[0] if bot_access else None,
    )


def _is_missing_access(detail: str | None) -> bool:
    if not detail:
        return False
    text = detail.casefold()
    return "50001" in text or "missing access" in text


async def _recreate_inaccessible_category(
    context: LayoutContext,
    resource: DesiredResource,
    existing: discord.CategoryChannel,
) -> ResourceApplyResult:
    """Delete a locked-out hub category and recreate it with desired overwrites."""
    try:
        await existing.delete(reason=f"{context.reason}: recreate inaccessible category")
    except discord.HTTPException as exc:
        return ResourceApplyResult(
            resource_id=resource.id,
            success=False,
            detail=f"inaccessible category (could not recreate): {exc}",
            channel=existing,
        )
    return await _ensure_category(context, resource, _allow_recreate=False)


async def _recreate_inaccessible_channel(
    context: LayoutContext,
    resource: DesiredResource,
    categories: dict[str, discord.CategoryChannel],
    existing: discord.TextChannel,
) -> ResourceApplyResult:
    """Delete a locked-out hub channel and recreate it (never for community slots)."""
    if resource.community_slot is not None:
        return ResourceApplyResult(
            resource_id=resource.id,
            success=False,
            detail=(
                "inaccessible community channel — grant the operator role "
                "View Channel on it, then re-run /server init"
            ),
            channel=existing,
        )
    try:
        await existing.delete(reason=f"{context.reason}: recreate inaccessible channel")
    except discord.HTTPException as exc:
        return ResourceApplyResult(
            resource_id=resource.id,
            success=False,
            detail=f"inaccessible channel (could not recreate): {exc}",
            channel=existing,
        )
    return await _ensure_channel(
        context,
        resource,
        categories,
        reconcile_only=False,
        _allow_recreate=False,
    )


def _find_category(
    guild: discord.Guild,
    resource: DesiredResource,
) -> discord.CategoryChannel | None:
    return find_channel(guild, resource.name, channel_type=discord.CategoryChannel)


def _find_text_channel(
    guild: discord.Guild,
    resource: DesiredResource,
    *,
    category: discord.CategoryChannel | None,
) -> discord.TextChannel | None:
    if resource.community_slot == "rules":
        rules = guild.rules_channel
        if isinstance(rules, discord.TextChannel):
            return rules
    if resource.community_slot == "public_updates":
        updates = guild.public_updates_channel
        if isinstance(updates, discord.TextChannel):
            return updates

    # Prefer in-category match
    if category is not None:
        match = find_channel(
            guild,
            resource.name,
            channel_type=discord.TextChannel,
            category_id=category.id,
        )
        if match is not None:
            return match

    return find_channel(guild, resource.name, channel_type=discord.TextChannel)


async def _ensure_category(
    context: LayoutContext,
    resource: DesiredResource,
    *,
    _allow_recreate: bool = True,
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
            managed_targets=resource.managed_targets,
            reason=context.reason,
        )
    except (discord.HTTPException, ValueError) as exc:
        detail = str(exc)
        if (
            _allow_recreate
            and existing is not None
            and resource.managed == "hub"
            and _is_missing_access(detail)
        ):
            return await _recreate_inaccessible_category(context, resource, existing)
        return ResourceApplyResult(
            resource_id=resource.id,
            success=False,
            detail=detail,
        )
    position_changed = False
    if resource.position is not None and result.resource.position != resource.position:
        try:
            await result.resource.edit(position=resource.position, reason=context.reason)
            position_changed = True
        except discord.HTTPException as exc:
            return ResourceApplyResult(
                resource_id=resource.id,
                success=False,
                changed=result.sync.changed,
                detail=str(exc),
                channel=result.resource,
            )
    sync_detail: str | None = "; ".join(result.sync.failures) or None
    if (
        not result.sync.success
        and _allow_recreate
        and existing is not None
        and resource.managed == "hub"
        and _is_missing_access(sync_detail)
    ):
        return await _recreate_inaccessible_category(context, resource, existing)
    return ResourceApplyResult(
        resource_id=resource.id,
        success=result.sync.success,
        changed=result.sync.changed or position_changed,
        detail=sync_detail,
        channel=result.resource,
    )


async def _ensure_channel(
    context: LayoutContext,
    resource: DesiredResource,
    categories: dict[str, discord.CategoryChannel],
    *,
    reconcile_only: bool,
    _allow_recreate: bool = True,
) -> ResourceApplyResult:
    perm = _permission_context(context)
    category = categories.get(resource.category_ref or "")
    existing = _find_text_channel(context.guild, resource, category=category)

    if existing is not None:
        wants_news = resource.kind is ResourceKind.ANNOUNCEMENT
        has_news = existing.is_news() is True
        if wants_news != has_news:
            if reconcile_only or resource.preserve_on_uninit or resource.community_slot is not None:
                return ResourceApplyResult(
                    resource_id=resource.id,
                    success=False,
                    detail="channel type does not match layout",
                    channel=existing,
                )
            try:
                await existing.delete(reason=f"{context.reason}: replace incorrect channel type")
            except discord.HTTPException as exc:
                return ResourceApplyResult(
                    resource_id=resource.id,
                    success=False,
                    detail=str(exc),
                    channel=existing,
                )
            existing = None

    if reconcile_only and existing is None:
        return ResourceApplyResult(
            resource_id=resource.id,
            success=False,
            detail="channel missing",
        )

    if existing is not None:
        # Apply identity edits (name/topic) separately from category moves.
        # Community rules/updates channels often reject category changes (50013);
        # bundling those with rename would leave the YAML name unapplied.
        identity_edits: dict[str, object] = {}
        if existing.name.casefold() != resource.name.casefold():
            identity_edits["name"] = resource.name
        if resource.topic is not None and getattr(existing, "topic", None) != resource.topic:
            identity_edits["topic"] = resource.topic

        category_edits: dict[str, object] = {}
        if category is not None and existing.category_id != category.id:
            category_edits["category"] = category

        meta_detail: str | None = None
        meta_changed = False

        if identity_edits:
            try:
                await existing.edit(reason=context.reason, **identity_edits)  # type: ignore[call-overload]
                meta_changed = True
            except discord.HTTPException as exc:
                meta_detail = f"rename: {exc}"

        if category_edits and meta_detail is None:
            try:
                await existing.edit(reason=context.reason, **category_edits)  # type: ignore[call-overload]
                meta_changed = True
            except discord.HTTPException as exc:
                # Keep going so permission sync can still run.
                meta_detail = f"placement: {exc}"

        try:
            sync = await permission_service.reconcile(
                existing,
                perm,
                resource.overwrites,
                managed_targets=resource.managed_targets,
                reason=context.reason,
            )
        except discord.HTTPException as exc:
            failure_detail = "; ".join(item for item in (meta_detail, str(exc)) if item)
            if (
                _allow_recreate
                and not reconcile_only
                and resource.managed == "hub"
                and _is_missing_access(failure_detail)
            ):
                return await _recreate_inaccessible_channel(
                    context, resource, categories, existing
                )
            return ResourceApplyResult(
                resource_id=resource.id,
                success=False,
                changed=meta_changed,
                detail=failure_detail,
                channel=existing,
            )

        details = [item for item in (meta_detail, *sync.failures) if item]
        sync_detail = "; ".join(details) if details else None
        if (
            not sync.success
            and _allow_recreate
            and not reconcile_only
            and resource.managed == "hub"
            and _is_missing_access(sync_detail)
        ):
            return await _recreate_inaccessible_channel(
                context, resource, categories, existing
            )
        return ResourceApplyResult(
            resource_id=resource.id,
            success=sync.success and meta_detail is None,
            changed=sync.changed or meta_changed,
            detail=sync_detail,
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
            managed_targets=resource.managed_targets,
            topic=resource.topic,
            news=resource.kind is ResourceKind.ANNOUNCEMENT,
            reason=context.reason,
        )
        if resource.community_slot == "rules":
            try:
                await context.guild.edit(rules_channel=result.resource, reason=context.reason)
            except discord.HTTPException:
                logger.warning("Could not bind guild rules_channel", exc_info=True)
        elif resource.community_slot == "public_updates":
            try:
                await context.guild.edit(
                    public_updates_channel=result.resource,
                    reason=context.reason,
                )
            except discord.HTTPException:
                logger.warning("Could not bind guild public_updates_channel", exc_info=True)
        return ResourceApplyResult(
            resource_id=resource.id,
            success=result.sync.success,
            changed=True,
            detail="; ".join(result.sync.failures) or None,
            channel=result.resource,
        )
    except (discord.HTTPException, ValueError) as exc:
        return ResourceApplyResult(
            resource_id=resource.id,
            success=False,
            detail=str(exc),
        )


async def _teardown_hub(
    context: LayoutContext,
    resources: list[DesiredResource],
) -> BatchApplyResult:
    from bot.core.discord.cleanup import delete_channel

    batch = BatchApplyResult()
    hub_category_names = {
        r.name.casefold()
        for r in resources
        if r.kind is ResourceKind.CATEGORY and r.managed == "hub"
    }
    preserve_names = {
        r.name.casefold() for r in resources if r.preserve_on_uninit or r.community_slot is not None
    }
    # Detach preserved/community channels from hub categories
    for channel in list(context.guild.text_channels):
        category = channel.category
        if category is None or category.name.casefold() not in hub_category_names:
            continue
        community_ids = {
            item.id
            for item in (
                context.guild.rules_channel,
                context.guild.public_updates_channel,
            )
            if isinstance(item, discord.TextChannel)
        }
        if channel.id in community_ids or channel.name.casefold() in preserve_names:
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
        community_ids = {
            item.id
            for item in (
                context.guild.rules_channel,
                context.guild.public_updates_channel,
            )
            if isinstance(item, discord.TextChannel)
        }
        if channel.id in community_ids or channel.name.casefold() in preserve_names:
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
                sync = await permission_service.reconcile(
                    existing,
                    perm,
                    resource.overwrites,
                    managed_targets=resource.managed_targets,
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

    if not reconcile_only and any(resource.managed == "hub" for resource in resources):
        from bot.app.layout.loader import load_layout
        from bot.core.discord.cleanup import delete_channel

        desired_names = {
            resource.name.casefold()
            for resource in resources
            if resource.kind is not ResourceKind.CATEGORY
        }
        retired = {name.casefold() for name in load_layout().retired_channels} - desired_names
        community_ids = {
            channel.id
            for channel in (context.guild.rules_channel, context.guild.public_updates_channel)
            if isinstance(channel, discord.TextChannel)
        }
        for channel in list(context.guild.text_channels):
            if channel.id in community_ids or channel.name.casefold() not in retired:
                continue
            deleted = await delete_channel(
                context.guild,
                channel.id,
                label=f"retired hub channel #{channel.name}",
            )
            batch.results.append(
                ResourceApplyResult(
                    resource_id=f"retired:{channel.name}",
                    success=deleted,
                    changed=deleted,
                    detail=None if deleted else "delete failed",
                )
            )

    return batch
