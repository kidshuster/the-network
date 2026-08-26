from __future__ import annotations

import importlib
from collections.abc import Iterator
from types import ModuleType
from typing import Any

from bot.app.recipes.registry import RecipeRegistry, collect_recipes

# Explicit, deterministic recipe modules (Architecture Contract Phase 4).
# Domain entry modules first; hub helpers remain until Phase 5 reclassification.
RECIPE_MODULES: tuple[str, ...] = (
    "bot.features.recipes.server",
    "bot.features.recipes.startup",
    "bot.features.recipes.network",
    "bot.features.recipes.client",
    "bot.features.recipes.subscription",
    "bot.features.recipes.onboarding",
    "bot.features.recipes.relay",
    "bot.app.widgets.ui_recipes",
    "bot.features.widgets.presenters",
    "bot.features.widgets.interaction_presenters",
    "bot.features.recipes.hub.initialize",
    "bot.features.recipes.hub.uninitialize",
    "bot.features.recipes.hub.migrate",
    "bot.features.recipes.hub.installs",
    "bot.features.recipes.hub.data_reset",
    "bot.features.recipes.hub.announcements",
    "bot.features.recipes.hub.client_announcements",
)


def discover_recipe_modules() -> Iterator[ModuleType]:
    for name in RECIPE_MODULES:
        yield importlib.import_module(name)


def build_recipe_registry(bot: Any) -> RecipeRegistry:
    """Build the runtime registry from the explicit feature module list."""
    registry = RecipeRegistry(bot)
    for module in discover_recipe_modules():
        registry.register_many(collect_recipes(module))
    return registry
