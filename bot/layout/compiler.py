from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import discord

from bot.layout.loader import load_layout, load_roles
from bot.layout.roles import LayoutContext, resolve_targets, validate_target
from bot.layout.schema import CategorySpec, ChannelSpec, CommunitySlot, ManagedKind
from bot.permissions.service import OverwriteMap, Target

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class ResourceKind(Enum):
    CATEGORY = "category"
    TEXT = "text"
    ANNOUNCEMENT = "announcement"


@dataclass(frozen=True)
class DesiredResource:
    id: str
    kind: ResourceKind
    name: str
    category_ref: str | None = None
    topic: str | None = None
    position: int | None = None
    overwrites: dict[Target, discord.PermissionOverwrite] = field(default_factory=dict)
    managed_targets: frozenset[Target] = frozenset()
    managed: ManagedKind = "hub"
    preserve_on_uninit: bool = False
    community_slot: CommunitySlot | None = None
    legacy_names: tuple[str, ...] = ()


def _substitute(text: str, context: LayoutContext) -> str:
    values: dict[str, Any] = {
        "server_name": context.server_name or "",
        "slug": context.slug or "",
        "network_key": context.network_key or "",
    }
    return _PLACEHOLDER_RE.sub(lambda match: str(values.get(match.group(1), match.group(0))), text)


def _merged_fields(
    logical_name: str,
    *overrides: dict[str, dict[str, bool | None] | None],
) -> dict[str, bool | None] | None:
    defaults = load_roles().roles[logical_name].permissions
    fields = dict(defaults)
    for layer in overrides:
        if logical_name not in layer:
            continue
        patch = layer[logical_name]
        if patch is None:
            return None
        fields.update(patch)
    return fields


def _compile_profile(
    context: LayoutContext,
    profile_name: str,
    *overrides: dict[str, dict[str, bool | None] | None],
) -> tuple[dict[Target, discord.PermissionOverwrite], frozenset[Target]]:
    roles_spec = load_roles()
    profile = load_layout().permission_profiles[profile_name]
    desired: dict[Target, discord.PermissionOverwrite] = {}
    owned: set[Target] = {context.bot_member}  # clean legacy member overwrites
    if context.operator_role is not None:
        owned.add(context.operator_role)  # clean the legacy operator overwrite
    for role_spec in roles_spec.roles.values():
        owned.update(resolve_targets(context, role_spec.target))
    for logical_name in profile.roles:
        role_spec = roles_spec.roles[logical_name]
        targets = resolve_targets(context, role_spec.target)
        validate_target(context, logical_name, role_spec.target, targets)
        fields = _merged_fields(logical_name, profile.overrides, *overrides)
        if fields is None:
            continue
        overwrite = discord.PermissionOverwrite(**fields)
        for target in targets:
            desired[target] = overwrite
    return desired, frozenset(owned)


def _category_resource(
    context: LayoutContext,
    resource_id: str,
    spec: CategorySpec,
    *,
    managed: ManagedKind,
) -> DesiredResource:
    overwrites, owned = _compile_profile(context, spec.profile, spec.overrides)
    return DesiredResource(
        id=resource_id,
        kind=ResourceKind.CATEGORY,
        name=_substitute(spec.name, context),
        position=spec.position,
        overwrites=overwrites,
        managed_targets=owned,
        managed=managed,
    )


def _channel_resource(
    context: LayoutContext,
    resource_id: str,
    spec: ChannelSpec,
    category_id: str,
    category: CategorySpec,
    *,
    managed: ManagedKind,
) -> DesiredResource | None:
    if spec.instances == "per_subscription" and not context.network_key:
        return None
    profile_name = spec.profile or category.profile
    inherited = category.overrides if spec.profile is None else {}
    overwrites, owned = _compile_profile(
        context,
        profile_name,
        inherited,
        spec.overrides,
    )
    kind = ResourceKind.ANNOUNCEMENT if spec.type == "announcement" else ResourceKind.TEXT
    return DesiredResource(
        id=resource_id,
        kind=kind,
        name=_substitute(spec.name, context),
        category_ref=category_id,
        topic=_substitute(spec.topic, context) if spec.topic else None,
        position=spec.position,
        overwrites=overwrites,
        managed_targets=owned,
        managed=managed,
        preserve_on_uninit=spec.lifecycle == "preserve",
        community_slot=spec.community_slot,
        legacy_names=tuple(spec.legacy_names),
    )


def compile_hub(context: LayoutContext) -> list[DesiredResource]:
    categories = load_layout().layout.categories
    resources: list[DesiredResource] = []
    for category_id, category in sorted(categories.items(), key=lambda item: item[1].position):
        resources.append(_category_resource(context, category_id, category, managed="hub"))
        for channel_id, channel in category.channels.items():
            resource = _channel_resource(
                context, channel_id, channel, category_id, category, managed="hub"
            )
            if resource is not None:
                resources.append(resource)
    return resources


def compile_hub_slice(
    context: LayoutContext,
    *,
    category_ids: set[str] | None = None,
    channel_ids: set[str] | None = None,
) -> list[DesiredResource]:
    resources = compile_hub(context)
    selected_channels = [
        item for item in resources
        if item.kind is not ResourceKind.CATEGORY
        and (channel_ids is None or item.id in channel_ids)
        and (category_ids is None or item.category_ref in category_ids)
    ]
    needed = {item.category_ref for item in selected_channels}
    return [
        item for item in resources
        if (item.kind is ResourceKind.CATEGORY and item.id in needed)
        or item in selected_channels
    ]


def compile_client(
    context: LayoutContext,
    *,
    include_subscribed: bool = False,
    channel_ids: set[str] | None = None,
) -> list[DesiredResource]:
    category = load_layout().layout.client_category
    channels: list[DesiredResource] = []
    for channel_id, channel in category.channels.items():
        if channel.instances == "per_subscription" and not include_subscribed:
            continue
        if channel_ids is not None and channel_id not in channel_ids:
            continue
        resource = _channel_resource(
            context, channel_id, channel, "client", category, managed="client"
        )
        if resource is not None:
            channels.append(resource)
    include_category = channel_ids is None or "client" in channel_ids or bool(channels)
    resources = [
        _category_resource(context, "client", category, managed="client")
    ] if include_category else []
    return [*resources, *channels]


def compile_overwrites_for_profile(
    context: LayoutContext,
    profile_name: str,
) -> OverwriteMap:
    return _compile_profile(context, profile_name)[0]
