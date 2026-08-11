from __future__ import annotations

from typing import Literal

import discord
from pydantic import BaseModel, ConfigDict, Field, model_validator

CommunitySlot = Literal["rules", "public_updates"]
ManagedKind = Literal["hub", "client"]
ChannelType = Literal["text", "announcement"]
InstanceKind = Literal["static", "per_client", "per_subscription"]
TargetKind = Literal[
    "everyone",
    "moderator",
    "bot_access",
    "current_client_role",
    "client_roles",
]


def _validate_overrides(
    overrides: dict[str, dict[str, bool | None] | None],
) -> None:
    valid = set(discord.Permissions.VALID_FLAGS)
    unknown = {
        permission
        for fields in overrides.values()
        if fields is not None
        for permission in fields
        if permission not in valid
    }
    if unknown:
        raise ValueError(f"unknown Discord permissions: {sorted(unknown)}")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleDefaultsSpec(StrictModel):
    target: TargetKind
    permissions: dict[str, bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _valid_permissions(self) -> RoleDefaultsSpec:
        unknown = set(self.permissions) - set(discord.Permissions.VALID_FLAGS)
        if unknown:
            raise ValueError(f"unknown Discord permissions: {sorted(unknown)}")
        return self


class RolesSpec(StrictModel):
    version: Literal[1]
    roles: dict[str, RoleDefaultsSpec]


class ProfileSpec(StrictModel):
    roles: list[str]
    overrides: dict[str, dict[str, bool | None] | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _valid_overrides(self) -> ProfileSpec:
        _validate_overrides(self.overrides)
        return self


class ChannelInstallSpec(StrictModel):
    """Opaque install refs resolved by features (sticky/view/guide/sync)."""

    sticky: str | None = None
    view: str | None = None
    guide: str | None = None
    sync: str | None = None

    @model_validator(mode="after")
    def _has_target(self) -> ChannelInstallSpec:
        if not any((self.sticky, self.view, self.guide, self.sync)):
            raise ValueError("install entry must set sticky, view, guide, or sync")
        return self


class ChannelSpec(StrictModel):
    name: str
    type: ChannelType = "text"
    topic: str | None = None
    profile: str | None = None
    overrides: dict[str, dict[str, bool | None] | None] = Field(default_factory=dict)
    community_slot: CommunitySlot | None = None
    lifecycle: Literal["managed", "preserve"] = "managed"
    position: int | None = None
    instances: InstanceKind = "static"
    legacy_names: list[str] = Field(default_factory=list)
    installs: list[ChannelInstallSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _community_is_preserved(self) -> ChannelSpec:
        _validate_overrides(self.overrides)
        if self.community_slot is not None:
            self.lifecycle = "preserve"
        return self


class CategorySpec(StrictModel):
    name: str
    # Hub categories set this explicitly. Client categories omit it so Discord
    # placement is controlled by compile/apply (below hub), not forced to 0.
    position: int | None = None
    profile: str
    overrides: dict[str, dict[str, bool | None] | None] = Field(default_factory=dict)
    channels: dict[str, ChannelSpec] = Field(default_factory=dict)
    legacy_names: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _valid_overrides(self) -> CategorySpec:
        _validate_overrides(self.overrides)
        return self


class LayoutResourcesSpec(StrictModel):
    categories: dict[str, CategorySpec]
    client_category: CategorySpec


class LayoutSpec(StrictModel):
    version: Literal[1]
    retired_channels: list[str] = Field(default_factory=list)
    permission_profiles: dict[str, ProfileSpec]
    layout: LayoutResourcesSpec

    @model_validator(mode="after")
    def _references_exist(self) -> LayoutSpec:
        profiles = set(self.permission_profiles)
        categories = [
            *self.layout.categories.items(),
            ("client_category", self.layout.client_category),
        ]
        for category_id, category in categories:
            if category.profile not in profiles:
                raise ValueError(f"{category_id}: unknown profile {category.profile!r}")
            for channel_id, channel in category.channels.items():
                if channel.profile is not None and channel.profile not in profiles:
                    raise ValueError(
                        f"{category_id}.{channel_id}: unknown profile {channel.profile!r}",
                    )
        slots = [
            channel.community_slot
            for category in self.layout.categories.values()
            for channel in category.channels.values()
            if channel.community_slot is not None
        ]
        if len(slots) != len(set(slots)):
            raise ValueError("each community_slot may appear at most once")
        desired_names = {
            channel.name.casefold()
            for category in self.layout.categories.values()
            for channel in category.channels.values()
        }
        category_names = {
            category.name.casefold() for category in self.layout.categories.values()
        }
        overlap = desired_names & {name.casefold() for name in self.retired_channels}
        if overlap:
            raise ValueError(f"active channels cannot be retired: {sorted(overlap)}")
        # Legacy aliases are kind-scoped: a channel may reuse a category's display name.
        for category_id, category in self.layout.categories.items():
            for legacy in category.legacy_names:
                if legacy.casefold() in category_names:
                    raise ValueError(
                        f"{category_id}: legacy_names entry {legacy!r} conflicts with an "
                        "active category name",
                    )
            for channel_id, channel in category.channels.items():
                for legacy in channel.legacy_names:
                    if legacy.casefold() in desired_names:
                        raise ValueError(
                            f"{category_id}.{channel_id}: legacy_names entry {legacy!r} "
                            "conflicts with an active channel name",
                        )
        return self
