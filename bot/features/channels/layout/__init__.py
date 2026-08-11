"""Feature-owned layout compile, apply, and configuration loading."""

from __future__ import annotations

from bot.features.channels.layout.applier import ApplyMode, BatchApplyResult, apply_layout
from bot.features.channels.layout.bindings import apply_migration_bindings
from bot.features.channels.layout.compiler import (
    DesiredResource,
    SubscriptionCompileInput,
    compile_client,
    compile_hub,
    compile_hub_slice,
)
from bot.features.channels.layout.inventory import gather_guild_inventory
from bot.features.channels.layout.loader import validate_all_layouts
from bot.features.channels.layout.managed import hub_category_names, preserved_channel_names
from bot.features.channels.layout.roles import LayoutContext

__all__ = [
    "ApplyMode",
    "BatchApplyResult",
    "DesiredResource",
    "LayoutContext",
    "SubscriptionCompileInput",
    "apply_layout",
    "apply_migration_bindings",
    "compile_client",
    "compile_hub",
    "compile_hub_slice",
    "gather_guild_inventory",
    "hub_category_names",
    "preserved_channel_names",
    "validate_all_layouts",
]
