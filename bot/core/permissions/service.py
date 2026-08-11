from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

import discord

Target = discord.Role | discord.Member | discord.Object
OverwriteMap = Mapping[Target, discord.PermissionOverwrite]
ReconcileTarget = discord.CategoryChannel | discord.TextChannel


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
    for target in desired:
        if isinstance(target, discord.Role) and not can_configure_role(context.bot_member, target):
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
        current_value = target.overwrites
        current: OverwriteMap = current_value if isinstance(current_value, Mapping) else {}
        final, preserved = _build_final_map(current, desired, managed_targets)
        added, updated, removed = _diff(current, desired, managed_targets)
        if not (added or updated or removed):
            return PermissionSyncResult(True, False, target.id, preserved=preserved, verified=True)
        try:
            await target.edit(overwrites=final, reason=reason)
        except discord.HTTPException as exc:
            return PermissionSyncResult(
                False, False, target.id, added, updated, removed, preserved, failures=(str(exc),)
            )
        return PermissionSyncResult(
            True, True, target.id, added, updated, removed, preserved, verified=True
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
    ) -> PermissionResourceResult[discord.TextChannel]:
        channel = existing
        if channel is None:
            blockers = _validate(context, overwrites)
            if blockers:
                raise ValueError("; ".join(blockers))
            kwargs: dict[str, object] = {
                "name": name,
                "reason": reason,
                "overwrites": dict(overwrites),
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
        return PermissionResourceResult(channel, sync)


permission_service = PermissionService()
