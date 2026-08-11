from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TriggerKind(StrEnum):
    SLASH = "slash"
    DISCORD_EVENT = "discord_event"
    APP_EVENT = "app_event"
    BUTTON = "button"
    MODAL = "modal"


RunRecipe = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class TriggerSpec:
    """Generic entry-point binding from a surface to a recipe name."""

    id: str
    kind: TriggerKind
    recipe: str
    # Slash
    slash_group: str | None = None
    slash_name: str | None = None
    slash_description: str | None = None
    slash_group_description: str = "The Network commands"
    default_permissions: tuple[str, ...] = ()
    ephemeral: bool = True
    background: bool = False
    presenter: str | None = None
    # Events
    event: str | None = None


class TriggerCatalogError(RuntimeError):
    pass


@dataclass
class TriggerCatalog:
    _by_id: dict[str, TriggerSpec] = field(default_factory=dict)
    _slash_keys: dict[tuple[str, str], str] = field(default_factory=dict)
    _events: dict[str, list[str]] = field(default_factory=dict)

    def register(self, spec: TriggerSpec) -> None:
        if spec.id in self._by_id:
            raise TriggerCatalogError(f"Duplicate trigger id {spec.id!r}")
        if spec.kind is TriggerKind.SLASH:
            if not spec.slash_group or not spec.slash_name:
                raise TriggerCatalogError(f"Slash trigger {spec.id!r} needs group and name")
            key = (spec.slash_group, spec.slash_name)
            if key in self._slash_keys:
                raise TriggerCatalogError(
                    f"Duplicate slash command {spec.slash_group}/{spec.slash_name}"
                )
            self._slash_keys[key] = spec.id
        if spec.kind in (TriggerKind.DISCORD_EVENT, TriggerKind.APP_EVENT):
            if not spec.event:
                raise TriggerCatalogError(f"Event trigger {spec.id!r} needs event name")
            self._events.setdefault(spec.event, []).append(spec.id)
        self._by_id[spec.id] = spec

    def register_many(self, specs: Iterable[TriggerSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def get(self, trigger_id: str) -> TriggerSpec:
        try:
            return self._by_id[trigger_id]
        except KeyError as exc:
            raise TriggerCatalogError(f"Unknown trigger {trigger_id!r}") from exc

    def list_by_kind(self, kind: TriggerKind) -> tuple[TriggerSpec, ...]:
        return tuple(spec for spec in self._by_id.values() if spec.kind is kind)

    def triggers_for_event(self, event: str) -> tuple[TriggerSpec, ...]:
        return tuple(self.get(trigger_id) for trigger_id in self._events.get(event, ()))

    def ids(self) -> frozenset[str]:
        return frozenset(self._by_id)


async def dispatch(
    catalog: TriggerCatalog,
    runner: RunRecipe,
    trigger_id: str,
    **payload: Any,
) -> Any:
    spec = catalog.get(trigger_id)
    return await runner(spec.recipe, **payload)


async def dispatch_event(
    catalog: TriggerCatalog,
    runner: RunRecipe,
    event: str,
    **payload: Any,
) -> list[Any]:
    results: list[Any] = []
    for spec in catalog.triggers_for_event(event):
        results.append(await runner(spec.recipe, **payload))
    return results
