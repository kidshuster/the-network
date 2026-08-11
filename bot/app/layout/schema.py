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

    @model_validator(mode="after")
    def _community_is_preserved(self) -> ChannelSpec:
        _validate_overrides(self.overrides)
        if self.community_slot is not None:
            self.lifecycle = "preserve"
        return self


class CategorySpec(StrictModel):
    name: str
    position: int = 0
    profile: str
    overrides: dict[str, dict[str, bool | None] | None] = Field(default_factory=dict)
    channels: dict[str, ChannelSpec] = Field(default_factory=dict)

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
        overlap = desired_names & {name.casefold() for name in self.retired_channels}
        if overlap:
            raise ValueError(f"active channels cannot be retired: {sorted(overlap)}")
        return self
