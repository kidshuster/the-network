from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecipeSpec:
    name: str
    interactions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecipeCallResult:
    recipe: str
    value: object = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
