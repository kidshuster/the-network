from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GuildInitResult:
    success: bool
    created_categories: list[str] = field(default_factory=list)
    created_channels: list[str] = field(default_factory=list)
    moved_channels: list[str] = field(default_factory=list)
    updated_roles: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    rectifications: list[str] = field(default_factory=list)
    rectification_skipped: list[str] = field(default_factory=list)
    rectification_failures: list[str] = field(default_factory=list)
    reason: str | None = None
