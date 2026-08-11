from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommandSpec:
    group: str
    name: str
    description: str
    default_permissions: tuple[str, ...] = ()
    ephemeral: bool = True
    background: bool = False
    presenter: str | None = None
    group_description: str = "The Network commands"


@dataclass(frozen=True)
class RecipeSpec:
    name: str
    command: CommandSpec | None = None
    events: tuple[str, ...] = ()
    interactions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecipeCallResult:
    recipe: str
    value: object = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
