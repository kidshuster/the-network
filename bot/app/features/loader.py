from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import bot.features
from bot.app.recipes.registry import RecipeRegistry, collect_recipes


def discover_recipe_modules() -> Iterator[ModuleType]:
    """Import every Python recipe module owned by the feature tree."""
    package = bot.features
    yield package
    for module in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
        yield importlib.import_module(module.name)


def build_recipe_registry(bot: Any) -> RecipeRegistry:
    """Build the runtime registry without a handwritten feature catalog."""
    registry = RecipeRegistry(bot)
    for module in discover_recipe_modules():
        registry.register_many(collect_recipes(module))
    return registry
