from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import bot


def _core_python_files() -> list[Path]:
    core_root = Path(bot.__file__).resolve().parent / "core"
    return sorted(core_root.rglob("*.py"))


def _imports_outer_workflows(source: str) -> list[str]:
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(
                ("bot.widgets", "bot.adapters", "bot.smoke")
            ):
                violations.append(f"from {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(
                    ("bot.widgets", "bot.adapters", "bot.smoke")
                ):
                    violations.append(f"import {alias.name}")
    return violations


def test_core_does_not_import_adapters_or_workflows() -> None:
    offenders: list[str] = []
    for path in _core_python_files():
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(Path(bot.__file__).resolve().parent.parent)
        source = path.read_text(encoding="utf-8")
        imports = _imports_outer_workflows(source)
        if imports:
            offenders.append(f"{rel}: {', '.join(imports)}")
    assert offenders == [], "core dependency violations:\n" + "\n".join(offenders)


def test_bot_modules_import_cleanly() -> None:
    package = Path(bot.__file__).resolve().parent
    for module in pkgutil.walk_packages([str(package)], prefix="bot."):
        if module.name.startswith("bot.smoke."):
            continue
        importlib.import_module(module.name)


def test_retired_yaml_recipe_runtime_does_not_return() -> None:
    package = Path(bot.__file__).resolve().parent
    recipes = package / "widgets" / "recipes"
    assert not list(recipes.rglob("*.yaml"))
    assert not (recipes / "engine.py").exists()
    assert not (recipes / "loader.py").exists()
    assert not (recipes / "schema.py").exists()

    forbidden = (
        "RecipeExecutor",
        "RecipeRunner",
        "RecipeEventRunner",
        "build_recipe_executor",
    )
    offenders: list[str] = []
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(name in source for name in forbidden):
            offenders.append(str(path.relative_to(package.parent)))
    assert offenders == []


def test_discord_event_adapters_dispatch_through_recipe_registry() -> None:
    event_adapter = (
        Path(bot.__file__).resolve().parent / "adapters" / "discord" / "events.py"
    ).read_text(encoding="utf-8")
    assert 'recipe_registry.dispatch("discord.message"' in event_adapter
    assert 'recipe_registry.dispatch("discord.webhooks_update"' in event_adapter


def test_legacy_packages_are_removed() -> None:
    package = Path(bot.__file__).resolve().parent
    for retired in ("cogs", "messages", "presentation", "recipes", "ui"):
        assert not list((package / retired).glob("*.py"))
    assert not (package / "core" / "layout").exists()
    assert not (package / "core" / "stickies").exists()
    assert not (package / "core" / "integrations").exists()
