from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ResourceKindName = Literal["category", "text", "announcement"]
CommunitySlotName = Literal["rules", "public_updates"]
BindingSource = Literal["managed_id", "community_slot", "alias"]


@dataclass(frozen=True)
class InventoryChannel:
    discord_id: int
    name: str
    kind: ResourceKindName
    parent_id: int | None = None


@dataclass(frozen=True)
class GuildInventory:
    channels: tuple[InventoryChannel, ...]
    rules_channel_id: int | None = None
    public_updates_channel_id: int | None = None

    def by_id(self) -> dict[int, InventoryChannel]:
        return {item.discord_id: item for item in self.channels}


@dataclass(frozen=True)
class DesiredMigrationResource:
    resource_key: str
    kind: ResourceKindName
    name: str
    aliases: tuple[str, ...] = ()
    category_key: str | None = None
    community_slot: CommunitySlotName | None = None


@dataclass(frozen=True)
class StoredResourceRef:
    resource_key: str
    discord_id: int
    discord_type: str


@dataclass(frozen=True)
class MigrationBinding:
    resource_key: str
    discord_id: int
    source: BindingSource
    current_name: str
    target_name: str
    category_key: str | None = None


@dataclass(frozen=True)
class AmbiguousMatch:
    resource_key: str
    candidate_ids: tuple[int, ...]
    candidate_names: tuple[str, ...]


@dataclass(frozen=True)
class DeleteCandidate:
    discord_id: int
    name: str
    kind: ResourceKindName


@dataclass(frozen=True)
class MigrationPlan:
    bindings: tuple[MigrationBinding, ...] = ()
    ambiguous: tuple[AmbiguousMatch, ...] = ()
    delete_candidates: tuple[DeleteCandidate, ...] = ()
    preserve_client: tuple[InventoryChannel, ...] = ()
    unmanaged: tuple[InventoryChannel, ...] = ()

    @property
    def needs_review(self) -> bool:
        # Exact retired-name deletes apply automatically. Only ambiguous maps
        # require operator review (Architecture Contract / Phase 2).
        return bool(self.ambiguous)

    def bound_ids(self) -> dict[str, int]:
        return {item.resource_key: item.discord_id for item in self.bindings}


def _alias_set(resource: DesiredMigrationResource) -> frozenset[str]:
    names = (resource.name, *resource.aliases)
    return frozenset(name.casefold() for name in names if name.strip())


def _kind_compatible(desired: ResourceKindName, actual: ResourceKindName) -> bool:
    if desired == "category":
        return actual == "category"
    if actual == "category":
        return False
    # text/announcement are interchangeable for migration matching
    return actual in {"text", "announcement"}


def _is_client_suspected(
    channel: InventoryChannel,
    *,
    client_discord_ids: frozenset[int],
    client_category_ids: frozenset[int],
) -> bool:
    if channel.discord_id in client_discord_ids:
        return True
    if channel.parent_id is not None and channel.parent_id in client_category_ids:
        return True
    return False


def build_migration_plan(
    inventory: GuildInventory,
    desired: tuple[DesiredMigrationResource, ...],
    *,
    stored: tuple[StoredResourceRef, ...] = (),
    retired_names: frozenset[str] = frozenset(),
    client_discord_ids: frozenset[int] = frozenset(),
    client_category_ids: frozenset[int] = frozenset(),
) -> MigrationPlan:
    """Match guild inventory to desired resources without version-specific branches."""
    by_id = inventory.by_id()
    claimed: set[int] = set()
    bindings: dict[str, MigrationBinding] = {}
    ambiguous: list[AmbiguousMatch] = []
    unbound = {resource.resource_key: resource for resource in desired}
    stored_by_key = {item.resource_key: item for item in stored}
    retired = {name.casefold() for name in retired_names}

    def bind(
        resource: DesiredMigrationResource,
        channel: InventoryChannel,
        source: BindingSource,
    ) -> None:
        bindings[resource.resource_key] = MigrationBinding(
            resource_key=resource.resource_key,
            discord_id=channel.discord_id,
            source=source,
            current_name=channel.name,
            target_name=resource.name,
            category_key=resource.category_key,
        )
        claimed.add(channel.discord_id)
        unbound.pop(resource.resource_key, None)

    for resource in list(unbound.values()):
        ref = stored_by_key.get(resource.resource_key)
        if ref is None:
            continue
        channel = by_id.get(ref.discord_id)
        if channel is None or channel.discord_id in claimed:
            continue
        if not _kind_compatible(resource.kind, channel.kind):
            continue
        bind(resource, channel, "managed_id")

    for resource in list(unbound.values()):
        if resource.community_slot is None:
            continue
        slot_id = (
            inventory.rules_channel_id
            if resource.community_slot == "rules"
            else inventory.public_updates_channel_id
        )
        if slot_id is None or slot_id in claimed:
            continue
        channel = by_id.get(slot_id)
        if channel is None or not _kind_compatible(resource.kind, channel.kind):
            continue
        bind(resource, channel, "community_slot")

    progress = True
    while progress and unbound:
        progress = False
        for resource in list(unbound.values()):
            aliases = _alias_set(resource)
            candidates = [
                channel
                for channel in inventory.channels
                if channel.discord_id not in claimed
                and _kind_compatible(resource.kind, channel.kind)
                and channel.name.casefold() in aliases
            ]
            if len(candidates) == 1:
                bind(resource, candidates[0], "alias")
                progress = True
            elif len(candidates) > 1:
                ambiguous.append(
                    AmbiguousMatch(
                        resource_key=resource.resource_key,
                        candidate_ids=tuple(item.discord_id for item in candidates),
                        candidate_names=tuple(item.name for item in candidates),
                    )
                )
                unbound.pop(resource.resource_key, None)

    preserve_client: list[InventoryChannel] = []
    delete_candidates: list[DeleteCandidate] = []
    unmanaged: list[InventoryChannel] = []
    for channel in inventory.channels:
        if channel.discord_id in claimed:
            continue
        if _is_client_suspected(
            channel,
            client_discord_ids=client_discord_ids,
            client_category_ids=client_category_ids,
        ):
            preserve_client.append(channel)
            continue
        if channel.name.casefold() in retired:
            delete_candidates.append(
                DeleteCandidate(
                    discord_id=channel.discord_id,
                    name=channel.name,
                    kind=channel.kind,
                )
            )
            continue
        unmanaged.append(channel)

    return MigrationPlan(
        bindings=tuple(bindings[key] for key in sorted(bindings)),
        ambiguous=tuple(ambiguous),
        delete_candidates=tuple(delete_candidates),
        preserve_client=tuple(preserve_client),
        unmanaged=tuple(unmanaged),
    )


def apply_manual_resolutions(
    plan: MigrationPlan,
    *,
    inventory: GuildInventory,
    desired: tuple[DesiredMigrationResource, ...],
    resolutions: dict[str, int],
    confirmed_delete_ids: frozenset[int] | None = None,
) -> MigrationPlan:
    """Apply operator picks for ambiguous resources and filter confirmed deletes."""
    by_id = inventory.by_id()
    desired_by_key = {item.resource_key: item for item in desired}
    claimed = {binding.discord_id for binding in plan.bindings}
    bindings = list(plan.bindings)
    remaining_ambiguous: list[AmbiguousMatch] = []

    for item in plan.ambiguous:
        chosen = resolutions.get(item.resource_key)
        resource = desired_by_key.get(item.resource_key)
        if chosen is None or resource is None:
            remaining_ambiguous.append(item)
            continue
        channel = by_id.get(chosen)
        if channel is None or chosen in claimed or chosen not in item.candidate_ids:
            remaining_ambiguous.append(item)
            continue
        bindings.append(
            MigrationBinding(
                resource_key=resource.resource_key,
                discord_id=channel.discord_id,
                source="alias",
                current_name=channel.name,
                target_name=resource.name,
                category_key=resource.category_key,
            )
        )
        claimed.add(chosen)

    deletes = plan.delete_candidates
    if confirmed_delete_ids is not None:
        deletes = tuple(
            item for item in plan.delete_candidates if item.discord_id in confirmed_delete_ids
        )

    return MigrationPlan(
        bindings=tuple(sorted(bindings, key=lambda item: item.resource_key)),
        ambiguous=tuple(remaining_ambiguous),
        delete_candidates=deletes,
        preserve_client=plan.preserve_client,
        unmanaged=plan.unmanaged,
    )
