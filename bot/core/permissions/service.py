from __future__ import annotations

import inspect
from collections.abc import Collection, Mapping
from dataclasses import dataclass

import discord

Target = discord.Role | discord.Member | discord.Object
OverwriteMap = Mapping[Target, discord.PermissionOverwrite]
ReconcileTarget = discord.CategoryChannel | discord.TextChannel

# Minimum member overwrite so the bot can rectify a private resource before
# role-based bot_access is confirmed. Never a permanent production grant.
_BOOTSTRAP_OVERWRITE = discord.PermissionOverwrite(
    view_channel=True,
    read_message_history=True,
    manage_channels=True,
    # Do not set manage_roles here: Discord rejects that bit in channel
    # overwrites unless the bot has Administrator. Guild Manage Roles is enough.
    send_messages=True,
    embed_links=True,
    attach_files=True,
    manage_messages=True,
    manage_webhooks=True,
)


def can_configure_role(bot_member: discord.Member, role: discord.Role) -> bool:
    return role.is_default() is True or (
        role.managed is not True
        and role.id != bot_member.top_role.id
        and (
            not isinstance(role.position, int)
            or not isinstance(bot_member.top_role.position, int)
            or bot_member.top_role.position > role.position
        )
    )


@dataclass(frozen=True)
class PermissionContext:
    guild: discord.Guild
    bot_member: discord.Member
    access_role: discord.Role | None = None
    moderator_role: discord.Role | None = None
    operator_role: discord.Role | None = None

    @property
    def bot_access_role(self) -> discord.Role | None:
        return self.operator_role


@dataclass(frozen=True)
class PermissionSyncResult:
    success: bool
    changed: bool
    target_id: int
    added: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    preserved: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    verified: bool = False


@dataclass(frozen=True)
class PermissionResourceResult[T]:
    resource: T
    sync: PermissionSyncResult


def build_context(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    access_role: discord.Role | None,
    moderator_role: discord.Role | None,
    operator_role: discord.Role | None = None,
) -> PermissionContext:
    return PermissionContext(guild, bot_member, access_role, moderator_role, operator_role)


def _identity(target: Target) -> tuple[str, int]:
    return ("member" if isinstance(target, discord.Member) else "role", target.id)


def _label(target: Target) -> str:
    return str(getattr(target, "name", f"{_identity(target)[0]}:{target.id}"))


def _same_overwrite(left: discord.PermissionOverwrite, right: discord.PermissionOverwrite) -> bool:
    left_allow, left_deny = left.pair()
    right_allow, right_deny = right.pair()
    return left_allow.value == right_allow.value and left_deny.value == right_deny.value


def _validate(context: PermissionContext, desired: OverwriteMap) -> tuple[str, ...]:
    blockers: list[str] = []
    if not context.bot_member.guild_permissions.manage_channels:
        blockers.append("Bot lacks Manage Channels.")
    access = context.bot_access_role
    if access is None:
        blockers.append("The configured bot-access role is unavailable.")
    elif not can_configure_role(context.bot_member, access):
        blockers.append(f"Bot-access role {access.name!r} is managed or above the bot.")
    top_role = context.bot_member.top_role
    for target in desired:
        if not isinstance(target, discord.Role):
            continue
        # Own top role (operator) may be granted channel access; Discord role hierarchy
        # checks do not apply the same way as editing a lower role.
        if top_role is not None and target.id == top_role.id:
            continue
        if not can_configure_role(context.bot_member, target):
            blockers.append(f"Role {target.name!r} is managed or above the bot.")
    return tuple(dict.fromkeys(blockers))


def _build_final_map(
    current: OverwriteMap,
    desired: OverwriteMap,
    managed_targets: Collection[Target],
) -> tuple[dict[Target, discord.PermissionOverwrite], tuple[str, ...]]:
    owned = {_identity(target) for target in managed_targets}
    final: dict[Target, discord.PermissionOverwrite] = {}
    preserved: list[str] = []
    for target, overwrite in current.items():
        if _identity(target) in owned:
            continue
        final[target] = overwrite
        preserved.append(_label(target))
    final.update(desired)
    return final, tuple(sorted(preserved))


def _diff(
    current: OverwriteMap,
    desired: OverwriteMap,
    managed_targets: Collection[Target],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    current_by_id = {
        _identity(target): (target, overwrite) for target, overwrite in current.items()
    }
    desired_by_id = {
        _identity(target): (target, overwrite) for target, overwrite in desired.items()
    }
    owned = {_identity(target) for target in managed_targets}
    added: list[str] = []
    updated: list[str] = []
    removed: list[str] = []
    for identity, (target, overwrite) in desired_by_id.items():
        previous = current_by_id.get(identity)
        if previous is None:
            added.append(_label(target))
        elif not _same_overwrite(previous[1], overwrite):
            updated.append(_label(target))
    for identity, (target, _) in current_by_id.items():
        if identity in owned and identity not in desired_by_id:
            removed.append(_label(target))
    return tuple(sorted(added)), tuple(sorted(updated)), tuple(sorted(removed))


def _current_map(target: ReconcileTarget) -> OverwriteMap:
    current_value = target.overwrites
    return current_value if isinstance(current_value, Mapping) else {}


def _overwrite_for(
    current: OverwriteMap,
    target: Target,
) -> discord.PermissionOverwrite | None:
    for existing, overwrite in current.items():
        if _identity(existing) == _identity(target):
            return overwrite
    return None


def _clamp_overwrite(
    bot_perms: discord.Permissions,
    overwrite: discord.PermissionOverwrite,
    *,
    current: discord.PermissionOverwrite | None = None,
) -> discord.PermissionOverwrite:
    """Drop allow/deny bits the bot cannot set; preserve current for those bits.

    Discord returns 50013 when an overwrite allow/deny includes a permission the
    bot lacks on that channel (common after @everyone lockdown).
    """
    clamped = discord.PermissionOverwrite()
    for name, value in overwrite:
        if value is None:
            continue
        if not getattr(bot_perms, name, False):
            if current is not None:
                preserved = getattr(current, name, None)
                if preserved is not None:
                    setattr(clamped, name, preserved)
            continue
        setattr(clamped, name, value)
    return clamped


def _clamp_desired_map(
    target: ReconcileTarget,
    bot_member: discord.Member,
    desired: OverwriteMap,
) -> dict[Target, discord.PermissionOverwrite]:
    perms = target.permissions_for(bot_member)
    if inspect.isawaitable(perms):
        return dict(desired)
    current = _current_map(target)
    return {
        item: _clamp_overwrite(
            perms,
            overwrite,
            current=_overwrite_for(current, item),
        )
        for item, overwrite in desired.items()
    }


def _bot_can_rectify(target: ReconcileTarget, bot_member: discord.Member) -> bool:
    """True when the bot can edit this resource's permission overwrites."""
    perms = target.permissions_for(bot_member)
    if inspect.isawaitable(perms):
        # permissions_for is synchronous in discord.py; async test doubles should not
        # force bootstrap. Treat as accessible and let the edit path surface real errors.
        return True
    view = getattr(perms, "view_channel", False)
    manage_channels = getattr(perms, "manage_channels", False)
    # Discord requires Manage Roles (channel Manage Permissions) to edit overwrites.
    manage_roles = getattr(perms, "manage_roles", False)
    if (
        inspect.isawaitable(view)
        or inspect.isawaitable(manage_channels)
        or inspect.isawaitable(manage_roles)
    ):
        return True
    return bool(view and manage_channels and manage_roles)


def _needs_bot_bootstrap(
    target: ReconcileTarget,
    context: PermissionContext,
    desired: OverwriteMap,
    managed_targets: Collection[Target],
) -> bool:
    """True when applying the canonical map may strand the bot without access."""
    if _bot_can_rectify(target, context.bot_member):
        member_ow = _overwrite_for(_current_map(target), context.bot_member)
        if member_ow is None:
            return False
        # Stale deny/allow member overwrite should still be replaced carefully.
        if member_ow.pair()[1].view_channel:
            return True
        removing_member = (
            _identity(context.bot_member) in {_identity(t) for t in managed_targets}
            and _identity(context.bot_member) not in {_identity(t) for t in desired}
        )
        return removing_member and not _role_access_already_desired(context, desired)
    return True


def _role_access_already_desired(
    context: PermissionContext,
    desired: OverwriteMap,
) -> bool:
    access = context.bot_access_role
    if access is None:
        return False
    for target, overwrite in desired.items():
        if _identity(target) != _identity(access):
            continue
        allow, _deny = overwrite.pair()
        return bool(allow.view_channel and allow.manage_channels)
    return False


async def _install_bot_bootstrap(
    target: ReconcileTarget,
    bot_member: discord.Member,
    *,
    reason: str,
) -> None:
    await target.set_permissions(
        bot_member,
        overwrite=_BOOTSTRAP_OVERWRITE,
        reason=f"{reason} (bot bootstrap)",
    )


async def _verify_bot_access(
    target: ReconcileTarget,
    context: PermissionContext,
) -> bool:
    refreshed: ReconcileTarget = target
    guild = context.guild
    fetch = getattr(guild, "fetch_channel", None)
    if fetch is not None:
        try:
            fetched = await fetch(target.id)
        except discord.HTTPException:
            fetched = None
        if isinstance(fetched, (discord.CategoryChannel, discord.TextChannel)):
            refreshed = fetched
    if not _bot_can_rectify(refreshed, context.bot_member):
        return False
    access = context.bot_access_role
    if access is None:
        return True
    # Prefer verifying role-based access once the canonical map is applied.
    overwrite = _overwrite_for(_current_map(refreshed), access)
    if overwrite is None:
        # Operator/top-role mirror may also carry access.
        operator = context.bot_member.top_role
        if operator is not None:
            overwrite = _overwrite_for(_current_map(refreshed), operator)
    if overwrite is None:
        # Effective permissions may still succeed via other roles.
        return True
    allow, deny = overwrite.pair()
    if deny.view_channel:
        return False
    return bool(allow.view_channel)


async def _strip_bot_member_overwrite(
    target: ReconcileTarget,
    context: PermissionContext,
    desired: OverwriteMap,
    managed_targets: Collection[Target],
    *,
    reason: str,
) -> None:
    if _identity(context.bot_member) not in {_identity(t) for t in managed_targets}:
        return
    if _identity(context.bot_member) in {_identity(t) for t in desired}:
        return
    if _overwrite_for(_current_map(target), context.bot_member) is None:
        return
    if not await _verify_bot_access(target, context):
        return
    await target.set_permissions(
        context.bot_member,
        overwrite=None,
        reason=f"{reason} (remove temporary bot member overwrite)",
    )


def _resource_label(target: ReconcileTarget) -> str:
    return str(getattr(target, "name", f"channel:{target.id}"))


async def _apply_overwrites_incrementally(
    channel: ReconcileTarget,
    current: OverwriteMap,
    desired: OverwriteMap,
    managed_targets: Collection[Target],
    *,
    bot_member: discord.Member,
    reason: str,
) -> None:
    """Apply owned overwrite diffs one target at a time when bulk replace fails."""
    current_by_id = {
        _identity(target): (target, overwrite) for target, overwrite in current.items()
    }
    desired_by_id = {
        _identity(target): (target, overwrite) for target, overwrite in desired.items()
    }
    owned = {_identity(target) for target in managed_targets}
    top_role_id = getattr(bot_member.top_role, "id", None)
    bot_member_id = _identity(bot_member)

    # Prefer bot-access role grants first, then other roles, then optional top-role.
    def _apply_order(
        item: tuple[tuple[str, int], tuple[Target, discord.PermissionOverwrite]],
    ) -> int:
        target = item[1][0]
        if (
            isinstance(target, discord.Role)
            and top_role_id is not None
            and target.id == top_role_id
        ):
            return 2
        overwrite = item[1][1]
        allow, _deny = overwrite.pair()
        if allow.manage_channels:
            return 0
        return 1

    for _, (target, overwrite) in sorted(desired_by_id.items(), key=_apply_order):
        previous = current_by_id.get(_identity(target))
        if previous is not None and _same_overwrite(previous[1], overwrite):
            continue
        try:
            await channel.set_permissions(
                target,  # type: ignore[arg-type]
                overwrite=overwrite,
                reason=reason,
            )
        except discord.HTTPException:
            # Top-role overwrites are best-effort; bot-access role is sufficient.
            if isinstance(target, discord.Role) and target.id == top_role_id:
                continue
            raise

    for identity, (target, _) in current_by_id.items():
        if identity not in owned or identity in desired_by_id:
            continue
        if identity == bot_member_id:
            # Caller strips bot-member overwrites only after effective access verifies.
            continue
        await channel.set_permissions(
            target,  # type: ignore[arg-type]
            overwrite=None,
            reason=reason,
        )


class PermissionService:
    """The sole production boundary for Discord permission mutation."""

    async def reconcile(
        self,
        target: ReconcileTarget,
        context: PermissionContext,
        desired: OverwriteMap,
        *,
        managed_targets: Collection[Target],
        reason: str,
    ) -> PermissionSyncResult:
        blockers = _validate(context, desired)
        if blockers:
            return PermissionSyncResult(
                False,
                False,
                target.id,
                blockers=blockers,
                failures=blockers,
            )
        current = _current_map(target)
        bootstrapped = False
        if _needs_bot_bootstrap(target, context, desired, managed_targets):
            try:
                await _install_bot_bootstrap(target, context.bot_member, reason=reason)
                bootstrapped = True
                current = _current_map(target)
            except discord.HTTPException as exc:
                return PermissionSyncResult(
                    False,
                    False,
                    target.id,
                    failures=(f"{_resource_label(target)}: bootstrap failed: {exc}",),
                )

        desired = _clamp_desired_map(target, context.bot_member, desired)
        final, preserved = _build_final_map(current, desired, managed_targets)
        added, updated, removed = _diff(current, desired, managed_targets)
        if not (added or updated or removed) and not bootstrapped:
            return PermissionSyncResult(True, False, target.id, preserved=preserved, verified=True)

        changed = bool(added or updated or removed or bootstrapped)
        try:
            await target.edit(overwrites=final, reason=reason)
        except discord.HTTPException:
            # Bulk replace often 50013/50001s when preserved unmanaged overwrites are
            # present or the channel is private; fall back to per-target edits.
            # If we skipped bootstrap because Manage Channels looked present but
            # Manage Roles was missing, install it before incremental edits.
            if not bootstrapped:
                try:
                    await _install_bot_bootstrap(
                        target, context.bot_member, reason=reason
                    )
                    bootstrapped = True
                    current = _current_map(target)
                    desired = _clamp_desired_map(target, context.bot_member, desired)
                    changed = True
                except discord.HTTPException as bootstrap_exc:
                    return PermissionSyncResult(
                        False,
                        False,
                        target.id,
                        added,
                        updated,
                        removed,
                        preserved,
                        failures=(
                            f"{_resource_label(target)}: bootstrap failed: {bootstrap_exc}",
                        ),
                    )
            try:
                await _apply_overwrites_incrementally(
                    target,
                    current,
                    desired,
                    managed_targets,
                    bot_member=context.bot_member,
                    reason=reason,
                )
            except discord.HTTPException as incremental_exc:
                return PermissionSyncResult(
                    False,
                    False,
                    target.id,
                    added,
                    updated,
                    removed,
                    preserved,
                    failures=(f"{_resource_label(target)}: {incremental_exc}",),
                )

        if not await _verify_bot_access(target, context):
            return PermissionSyncResult(
                False,
                changed,
                target.id,
                added,
                updated,
                removed,
                preserved,
                failures=(
                    f"{_resource_label(target)}: bot still lacks Manage Channels after reconcile.",
                ),
            )

        try:
            await _strip_bot_member_overwrite(
                target,
                context,
                desired,
                managed_targets,
                reason=reason,
            )
        except discord.HTTPException as exc:
            return PermissionSyncResult(
                False,
                changed,
                target.id,
                added,
                updated,
                removed,
                preserved,
                failures=(
                    f"{_resource_label(target)}: could not clear bot member overwrite: {exc}",
                ),
                verified=True,
            )

        return PermissionSyncResult(
            True, changed, target.id, added, updated, removed, preserved, verified=True
        )

    async def ensure_category(
        self,
        guild: discord.Guild,
        context: PermissionContext,
        *,
        existing: discord.CategoryChannel | None,
        name: str,
        overwrites: OverwriteMap,
        managed_targets: Collection[Target],
        reason: str,
        position: int | None = None,
    ) -> PermissionResourceResult[discord.CategoryChannel]:
        category = existing
        if category is None:
            blockers = _validate(context, overwrites)
            if blockers:
                raise ValueError("; ".join(blockers))
            category = await guild.create_category(
                name=name,
                overwrites=dict(overwrites),
                reason=reason,
            )
        sync = await self.reconcile(
            category, context, overwrites, managed_targets=managed_targets, reason=reason
        )
        if position is not None and category.position != position:
            try:
                await category.edit(position=position, reason=reason)
            except discord.HTTPException as exc:
                return PermissionResourceResult(
                    category,
                    PermissionSyncResult(
                        False,
                        sync.changed,
                        category.id,
                        sync.added,
                        sync.updated,
                        sync.removed,
                        sync.preserved,
                        failures=(*sync.failures, str(exc)),
                    ),
                )
        return PermissionResourceResult(category, sync)

    async def ensure_text_channel(
        self,
        guild: discord.Guild,
        context: PermissionContext,
        *,
        existing: discord.TextChannel | None,
        name: str,
        category: discord.CategoryChannel | None,
        overwrites: OverwriteMap,
        managed_targets: Collection[Target],
        reason: str,
        topic: str | None = None,
        news: bool = False,
        position: int | None = None,
    ) -> PermissionResourceResult[discord.TextChannel]:
        channel = existing
        if channel is None:
            blockers = _validate(context, overwrites)
            if blockers:
                raise ValueError("; ".join(blockers))
            # Create without overwrites first — Discord often 50013s when supplying
            # private overwrites at create time inside a permissioned category.
            kwargs: dict[str, object] = {
                "name": name,
                "reason": reason,
            }
            if category is not None:
                kwargs["category"] = category
            if topic is not None:
                kwargs["topic"] = topic
            if news:
                kwargs["news"] = True
            channel = await guild.create_text_channel(**kwargs)  # type: ignore[arg-type]
        sync = await self.reconcile(
            channel, context, overwrites, managed_targets=managed_targets, reason=reason
        )
        if position is not None and channel.position != position:
            try:
                await channel.edit(position=position, reason=reason)
            except discord.HTTPException as exc:
                return PermissionResourceResult(
                    channel,
                    PermissionSyncResult(
                        False,
                        sync.changed,
                        channel.id,
                        sync.added,
                        sync.updated,
                        sync.removed,
                        sync.preserved,
                        failures=(*sync.failures, str(exc)),
                    ),
                )
        return PermissionResourceResult(channel, sync)


permission_service = PermissionService()
