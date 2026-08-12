from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

Primitive = str | int | bool | None

__all__ = [
    "ButtonSpec",
    "ButtonStyle",
    "DismissMessage",
    "OpenEphemeralView",
    "OpenModal",
    "Primitive",
    "RecipeHandler",
    "SelectOptionSpec",
    "SelectSpec",
    "recipe_handler",
]
ButtonStyle = Literal["primary", "secondary", "success", "danger", "link"]


@dataclass(frozen=True)
class RecipeHandler:
    recipe: str
    arguments: Mapping[str, Primitive] = field(default_factory=dict)


def recipe_handler(recipe: str, **arguments: Primitive) -> RecipeHandler:
    name = recipe.strip()
    if not name:
        raise ValueError("recipe name is required")
    for key, value in arguments.items():
        if value is not None and not isinstance(value, (str, int, bool)):
            raise TypeError(f"handler argument {key!r} must be a primitive")
    return RecipeHandler(recipe=name, arguments=dict(arguments))


@dataclass(frozen=True)
class ButtonSpec:
    tag: str
    label: str
    style: ButtonStyle = "secondary"
    handler: RecipeHandler | None = None
    disabled: bool = False
    row: int | None = None
    emoji: str | None = None


@dataclass(frozen=True)
class SelectOptionSpec:
    label: str
    value: str
    description: str | None = None
    emoji: str | None = None
    default: bool = False


@dataclass(frozen=True)
class SelectSpec:
    tag: str
    placeholder: str
    options: tuple[SelectOptionSpec, ...]
    handler: RecipeHandler
    min_values: int = 1
    max_values: int = 1
    row: int | None = None


@dataclass(frozen=True)
class OpenModal:
    template_id: str
    submit: RecipeHandler
    values: Mapping[str, Primitive] = field(default_factory=dict)
    defaults: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OpenEphemeralView:
    template_id: str
    content: str | None = None
    values: Mapping[str, Primitive] = field(default_factory=dict)
    bindings: Mapping[str, RecipeHandler] = field(default_factory=dict)
    slots: Mapping[str, Sequence[ButtonSpec | SelectSpec]] = field(default_factory=dict)


@dataclass(frozen=True)
class DismissMessage:
    content: str = "Cancelled."
