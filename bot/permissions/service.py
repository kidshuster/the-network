from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

import discord

Target = discord.Role | discord.Member | discord.Object
OverwriteMap = Mapping[
    discord.Role | discord.Member | discord.Object,
    discord.PermissionOverwrite,
]


def can_configure_role(bot_member: discord.Member, role: discord.Role) -> bool:
    if role.is_default():
        return True
    if bot_member.top_role.id == role.id:
        return False
    return bot_member.top_role.position > role.position


class ResourceKind(Enum):
    CATEGORY = "category"
    TEXT = "text"


@dataclass(frozen=True)
class PermissionContext:
    guild: discord.Guild
    bot_member: discord.Member
    access_role: discord.Role | None = None
    moderator_role: discord.Role | None = None
    operator_role: discord.Role | None = None

    @property
    def bot_access_role(self) -> discord.Role:
        if self.operator_role is not None:
            return self.operator_role
        return self.bot_member.top_role


@dataclass(frozen=True)
class PermissionSyncResult:
    success: bool
    changed: bool
    target_id: int
    failures: tuple[str, ...] = ()


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
    return PermissionContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access_role,
        moderator_role=moderator_role,
        operator_role=operator_role,
    )


def applicable_overwrites(
    context: PermissionContext,
    desired: Mapping[Target, discord.PermissionOverwrite],
    *,
    kind: ResourceKind,
    for_category_create: bool = False,
) -> dict[Target, discord.PermissionOverwrite]:
    """Single filter replacing strip/prepare/filter_configurable divergence."""
    bot = context.bot_member
    access = context.bot_access_role
    filtered: dict[Target, discord.PermissionOverwrite] = {}
    for target, overwrite in desired.items():
        if isinstance(target, discord.Member):
            if kind is ResourceKind.CATEGORY and not for_category_create:
                if target.id == bot.id:
                    filtered[target] = overwrite
            continue
        if not isinstance(target, discord.Role):
            filtered[target] = overwrite
            continue
        if for_category_create and (target.id == bot.id or target.id == access.id):
            continue
        if kind is not ResourceKind.CATEGORY and target.id == bot.id:
            continue
        if can_configure_role(bot, target) or target.id == access.id:
            filtered[target] = overwrite
        elif target.is_default():
            filtered[target] = overwrite
    return filtered


class PermissionService:
    async def reconcile_map(
        self,
        target: discord.abc.GuildChannel,
        context: PermissionContext,
        overwrites: OverwriteMap,
        *,
        reason: str,
        inherit: bool = False,
    ) -> PermissionSyncResult:
        if not context.bot_member.guild_permissions.manage_channels:
            return PermissionSyncResult(
                success=False,
                changed=False,
                target_id=target.id,
                failures=("Bot lacks Manage Channels.",),
            )

        kind = (
            ResourceKind.CATEGORY
            if isinstance(target, discord.CategoryChannel)
            else ResourceKind.TEXT
        )
        if inherit and isinstance(target, discord.TextChannel):
            await target.edit(sync_permissions=True, reason=reason)
            return PermissionSyncResult(success=True, changed=True, target_id=target.id)

        applicable = applicable_overwrites(context, overwrites, kind=kind)
        if _matches(target, applicable):
            return PermissionSyncResult(success=True, changed=False, target_id=target.id)

        failures: list[str] = []
        changed = False
        if isinstance(target, discord.CategoryChannel):
            try:
                await target.edit(overwrites=applicable, reason=reason)
                changed = True
            except discord.HTTPException as exc:
                failures.extend(
                    await _apply_incremental(target, applicable, context, reason=reason),
                )
                if not failures:
                    failures.append(str(exc))
        else:
            changed, channel_failures = await _sync_text_channel(
                target,
                applicable,
                context,
                reason=reason,
            )
            failures.extend(channel_failures)

        return PermissionSyncResult(
            success=not failures,
            changed=changed,
            target_id=target.id,
            failures=tuple(failures),
        )

    async def ensure_category(
        self,
        guild: discord.Guild,
        context: PermissionContext,
        *,
        existing: discord.CategoryChannel | None,
        name: str,
        overwrites: OverwriteMap,
        reason: str,
    ) -> PermissionResourceResult[discord.CategoryChannel]:
        if existing is not None:
            sync = await self.reconcile_map(existing, context, overwrites, reason=reason)
            return PermissionResourceResult(resource=existing, sync=sync)

        create_map = applicable_overwrites(
            context,
            overwrites,
            kind=ResourceKind.CATEGORY,
            for_category_create=True,
        )
        category = await guild.create_category(
            name=name,
            overwrites=create_map,
            reason=reason,
        )
        sync = await self.reconcile_map(category, context, overwrites, reason=reason)
        return PermissionResourceResult(resource=category, sync=sync)

    async def ensure_text_channel(
        self,
        guild: discord.Guild,
        context: PermissionContext,
        *,
        existing: discord.TextChannel | None,
        name: str,
        category: discord.CategoryChannel | None,
        overwrites: OverwriteMap,
        reason: str,
        topic: str | None = None,
        news: bool = False,
    ) -> PermissionResourceResult[discord.TextChannel]:
        from bot.hub.notifications import ensure_guild_only_mention_notifications

        await ensure_guild_only_mention_notifications(
            guild,
            context.bot_member,
            reason=reason,
        )

        channel = existing
        if channel is None:
            kwargs: dict[str, object] = {"name": name, "reason": reason}
            if category is not None:
                kwargs["category"] = category
            if topic is not None:
                kwargs["topic"] = topic
            if news:
                kwargs["news"] = True
            channel = await guild.create_text_channel(**kwargs)  # type: ignore[arg-type]
        else:
            if category is not None and channel.category_id != category.id:
                await channel.edit(category=category, reason=reason)
            if channel.name != name:
                await channel.edit(name=name, reason=reason)

        sync = await self.reconcile_map(channel, context, overwrites, reason=reason)
        return PermissionResourceResult(resource=channel, sync=sync)


def _matches(
    target: discord.abc.GuildChannel,
    desired: Mapping[Target, discord.PermissionOverwrite],
) -> bool:
    current = target.overwrites
    for key, overwrite in desired.items():
        if key not in current:
            return False
        if current[key].pair()[0].value != overwrite.pair()[0].value:
            return False
        if current[key].pair()[1].value != overwrite.pair()[1].value:
            return False
    return True


async def _sync_text_channel(
    channel: discord.abc.GuildChannel,
    applicable: Mapping[Target, discord.PermissionOverwrite],
    context: PermissionContext,
    *,
    reason: str,
) -> tuple[bool, list[str]]:
    if not isinstance(channel, discord.TextChannel):
        return False, ["Target is not a text channel."]
    if (
        channel.category_id is not None
        and not getattr(channel, "sync_permissions", True)
    ):
        try:
            await channel.edit(sync_permissions=True, reason=reason)
        except discord.HTTPException:
            pass

    async def _bulk() -> None:
        await channel.edit(overwrites=dict(applicable), sync_permissions=False, reason=reason)

    try:
        await _bulk()
        return True, []
    except discord.HTTPException as bulk_exc:
        if channel.category_id is None:
            return False, [str(bulk_exc)]
        try:
            await channel.edit(sync_permissions=True, reason=reason)
            await _bulk()
            return True, []
        except discord.HTTPException:
            failures = await _apply_incremental(
                channel,
                applicable,
                context,
                reason=reason,
            )
            return not failures, failures


async def _apply_incremental(
    target: discord.abc.GuildChannel,
    applicable: Mapping[Target, discord.PermissionOverwrite],
    context: PermissionContext,
    *,
    reason: str,
) -> list[str]:
    failures: list[str] = []
    access = context.bot_access_role
    for subject, overwrite in applicable.items():
        if isinstance(subject, discord.Object):
            continue
        if isinstance(subject, discord.Role) and subject.id == access.id:
            if subject.id == context.bot_member.top_role.id:
                continue
        try:
            await target.set_permissions(subject, overwrite=overwrite, reason=reason)
        except discord.HTTPException as exc:
            name = getattr(subject, "name", str(subject))
            failures.append(f"{name}: {exc}")
    return failures


permission_service = PermissionService()
