from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

RoleKey = Literal["everyone", "access", "operator", "moderator", "bot", "client"]
ClientScope = Literal["this_client", "all_clients"]
CommunitySlot = Literal["rules", "moderators"]
ManagedKind = Literal["hub", "client"]
ChannelType = Literal["text", "announcement"]
ApplyWhen = Literal["always", "subscribed"]


class OverwriteBindingSpec(BaseModel):
    role: RoleKey
    preset: str
    scope: ClientScope | None = None
    extras: dict[str, bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _client_scope_required(self) -> OverwriteBindingSpec:
        if self.role == "client" and self.scope is None:
            raise ValueError("client role bindings require scope: this_client|all_clients")
        if self.role != "client" and self.scope is not None:
            raise ValueError("scope is only valid for role: client")
        return self


class CategorySpec(BaseModel):
    id: str
    name: str
    position: int = 0
    managed: ManagedKind = "hub"
    overwrites: list[OverwriteBindingSpec] = Field(default_factory=list)


class ChannelSpec(BaseModel):
    id: str
    name: str
    category: str
    type: ChannelType = "text"
    topic: str | None = None
    inherit: bool = False
    managed: ManagedKind = "hub"
    preserve_on_uninit: bool = False
    community_slot: CommunitySlot | None = None
    legacy_names: list[str] = Field(default_factory=list)
    overwrites: list[OverwriteBindingSpec] = Field(default_factory=list)
    when: ApplyWhen = "always"
    position: int | None = None

    @model_validator(mode="after")
    def _community_implies_preserve(self) -> ChannelSpec:
        if self.community_slot is not None:
            self.preserve_on_uninit = True
        return self


class HubLayoutSpec(BaseModel):
    kind: Literal["hub_layout"] = "hub_layout"
    categories: list[CategorySpec]
    channels: list[ChannelSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids_and_slots(self) -> HubLayoutSpec:
        cat_ids = [c.id for c in self.categories]
        if len(cat_ids) != len(set(cat_ids)):
            raise ValueError("duplicate category id in hub_layout")
        ch_ids = [c.id for c in self.channels]
        if len(ch_ids) != len(set(ch_ids)):
            raise ValueError("duplicate channel id in hub_layout")
        slots = [c.community_slot for c in self.channels if c.community_slot is not None]
        if len(slots) != len(set(slots)):
            raise ValueError("each community_slot may appear at most once")
        known = set(cat_ids)
        for channel in self.channels:
            if channel.category not in known:
                raise ValueError(f"channel {channel.id} references unknown category")
        return self


class ClientCategorySpec(BaseModel):
    name: str
    overwrites: list[OverwriteBindingSpec] = Field(default_factory=list)


class ClientLayoutSpec(BaseModel):
    kind: Literal["client_layout"] = "client_layout"
    managed: ManagedKind = "client"
    category: ClientCategorySpec
    channels: list[ChannelSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _client_channels(self) -> ClientLayoutSpec:
        for channel in self.channels:
            channel.managed = "client"
            if channel.category != "client":
                # allow shorthand: treat missing/other as client category
                channel.category = "client"
        return self


class PermissionPresetsSpec(BaseModel):
    kind: Literal["permission_presets"] = "permission_presets"
    presets: dict[str, dict[str, Any]]


LayoutSpec = HubLayoutSpec | ClientLayoutSpec | PermissionPresetsSpec
