from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

Primitive = str | int | bool | None
ButtonStyle = Literal["primary", "secondary", "success", "danger", "link"]


@dataclass(frozen=True)
class ActionBinding:
    action: str
    arguments: Mapping[str, Primitive] = field(default_factory=dict)


@dataclass(frozen=True)
class ButtonSpec:
    id: str
    label: str
    style: ButtonStyle = "secondary"
    action: ActionBinding | None = None
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
    id: str
    placeholder: str
    options: tuple[SelectOptionSpec, ...]
    action: ActionBinding
    min_values: int = 1
    max_values: int = 1
    row: int | None = None
