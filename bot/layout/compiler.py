from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import discord

from bot.layout.loader import load_client_layout, load_hub_layout, load_presets
from bot.layout.roles import LayoutContext, resolve_binding_targets
from bot.layout.schema import (
    ApplyWhen,
    ChannelSpec,
    CommunitySlot,
    ManagedKind,
    OverwriteBindingSpec,
)
from bot.permissions.service import OverwriteMap, can_configure_role

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
    overwrites: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = field(default_factory=dict)
    inherit: bool = False
    managed: ManagedKind = "hub"
    preserve_on_uninit: bool = False
    community_slot: CommunitySlot | None = None
    legacy_names: tuple[str, ...] = ()
    when: ApplyWhen = "always"


def _substitute(text: str, ctx: dict[str, Any]) -> str:
    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in ctx:
            return match.group(0)
        value = ctx[key]
        if value is None:
            return ""
        return str(value)

    return _PLACEHOLDER_RE.sub(replacer, text)


def preset_overwrite(
    preset_name: str,
    extras: dict[str, bool | None] | None = None,
) -> discord.PermissionOverwrite:
    presets = load_presets().presets
    if preset_name not in presets:
        raise KeyError(f"Unknown permission preset: {preset_name}")
    fields = dict(presets[preset_name])
    if extras:
        fields.update(extras)
    return discord.PermissionOverwrite(**fields)


def _preset_overwrite(
    preset_name: str,
    extras: dict[str, bool | None],
) -> discord.PermissionOverwrite:
    return preset_overwrite(preset_name, extras)


def _include_target(
    context: LayoutContext,
    target: discord.Role | discord.Member,
) -> bool:
    if isinstance(target, discord.Member):
        return True
    if target.is_default():
        return True
    if context.operator_role is not None and target.id == context.operator_role.id:
        return True
    if context.access_role is not None and target.id == context.access_role.id:
        return True
    return can_configure_role(context.bot_member, target)


def _compile_overwrites(
    context: LayoutContext,
    bindings: list[OverwriteBindingSpec],
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    result: dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite] = {}
    for binding in bindings:
        overwrite = _preset_overwrite(binding.preset, binding.extras)
        for target in resolve_binding_targets(context, binding):
            if _include_target(context, target):
                result[target] = overwrite
    return result


def _placeholder_ctx(context: LayoutContext) -> dict[str, Any]:
    return {
        "server_name": context.server_name or "",
        "slug": context.slug or "",
        "network_key": context.network_key or "",
    }


def _channel_resource(
    context: LayoutContext,
    spec: ChannelSpec,
    *,
    category_ref: str,
) -> DesiredResource | None:
    if spec.when == "subscribed" and not context.network_key:
        return None
    placeholders = _placeholder_ctx(context)
    name = _substitute(spec.name, placeholders)
    topic = _substitute(spec.topic, placeholders) if spec.topic else None
    kind = (
        ResourceKind.ANNOUNCEMENT
        if spec.type == "announcement"
        else ResourceKind.TEXT
    )
    return DesiredResource(
        id=spec.id,
        kind=kind,
        name=name,
        category_ref=category_ref,
        topic=topic,
        position=spec.position,
        overwrites=_compile_overwrites(context, spec.overwrites),
        inherit=spec.inherit,
        managed=spec.managed,
        preserve_on_uninit=spec.preserve_on_uninit or spec.community_slot is not None,
        community_slot=spec.community_slot,
        legacy_names=tuple(spec.legacy_names),
        when=spec.when,
    )


def compile_hub(context: LayoutContext) -> list[DesiredResource]:
    hub = load_hub_layout()
    resources: list[DesiredResource] = []
    for category in sorted(hub.categories, key=lambda item: item.position):
        resources.append(
            DesiredResource(
                id=category.id,
                kind=ResourceKind.CATEGORY,
                name=category.name,
                position=category.position,
                overwrites=_compile_overwrites(context, category.overwrites),
                managed=category.managed,
            )
        )
    for channel in hub.channels:
        resource = _channel_resource(context, channel, category_ref=channel.category)
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
    selected: list[DesiredResource] = []
    for resource in resources:
        if resource.kind is ResourceKind.CATEGORY:
            if category_ids is not None and resource.id in category_ids:
                selected.append(resource)
            continue
        if channel_ids is not None and resource.id not in channel_ids:
            continue
        if category_ids is not None and resource.category_ref not in category_ids:
            continue
        selected.append(resource)
    if channel_ids is not None:
        needed = {r.category_ref for r in selected if r.category_ref}
        for resource in resources:
            if (
                resource.kind is ResourceKind.CATEGORY
                and resource.id in needed
                and resource not in selected
            ):
                selected.insert(0, resource)
    return selected


def compile_client(
    context: LayoutContext,
    *,
    include_subscribed: bool = False,
    channel_ids: set[str] | None = None,
) -> list[DesiredResource]:
    layout = load_client_layout()
    placeholders = _placeholder_ctx(context)
    channels: list[DesiredResource] = []
    for channel in layout.channels:
        if channel.when == "subscribed" and not include_subscribed:
            continue
        if channel_ids is not None and channel.id not in channel_ids:
            continue
        resource = _channel_resource(context, channel, category_ref="client")
        if resource is not None:
            channels.append(resource)

    # Always include the client category when compiling channels so the applier
    # can place new channels; omit only when the caller asked for nothing.
    include_category = channel_ids is None or "client" in channel_ids or bool(channels)
    resources: list[DesiredResource] = []
    if include_category:
        resources.append(
            DesiredResource(
                id="client",
                kind=ResourceKind.CATEGORY,
                name=_substitute(layout.category.name, placeholders),
                overwrites=_compile_overwrites(context, layout.category.overwrites),
                managed="client",
            )
        )
    resources.extend(channels)
    return resources


def compile_overwrites_for_bindings(
    context: LayoutContext,
    bindings: list[OverwriteBindingSpec],
) -> OverwriteMap:
    return _compile_overwrites(context, bindings)
