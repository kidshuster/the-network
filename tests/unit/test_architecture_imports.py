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
            if node.module and node.module.startswith("tests.core"):
                violations.append(f"from {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("tests.core"):
                    violations.append(f"import {alias.name}")
    return violations


def _imports_forbidden_layer(source: str, prefixes: tuple[str, ...]) -> list[str]:
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(prefixes):
                violations.append(f"from {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(prefixes):
                    violations.append(f"import {alias.name}")
    return violations


def test_core_does_not_import_adapters_or_workflows() -> None:
    offenders: list[str] = []
    for path in _core_python_files():
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(Path(bot.__file__).resolve().parent.parent)
        source = path.read_text(encoding="utf-8")
        imports = [
            *_imports_outer_workflows(source),
            *_imports_forbidden_layer(source, ("bot.app", "bot.features")),
        ]
        if imports:
            offenders.append(f"{rel}: {', '.join(imports)}")
    assert offenders == [], "core dependency violations:\n" + "\n".join(offenders)


def test_bot_modules_import_cleanly() -> None:
    package = Path(bot.__file__).resolve().parent
    for module in pkgutil.walk_packages([str(package)], prefix="bot."):
        if module.name.startswith("tests.core."):
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


def test_discord_event_adapters_dispatch_through_trigger_catalog() -> None:
    event_adapter = (
        Path(bot.__file__).resolve().parent
        / "app"
        / "discord"
        / "events.py"
    ).read_text(encoding="utf-8")
    assert 'dispatch_event("discord.message"' in event_adapter
    assert 'dispatch_event("discord.webhooks_update"' in event_adapter


def test_features_do_not_declare_command_or_invocation_decorators() -> None:
    package = Path(bot.__file__).resolve().parent / "features"
    offenders: list[str] = []
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "@command(" in source or "@invocation(" in source:
            offenders.append(str(path.relative_to(package.parent)))
    assert offenders == []


def test_app_owns_trigger_entry_catalog() -> None:
    triggers = Path(bot.__file__).resolve().parent / "app" / "triggers"
    assert (triggers / "slash.py").is_file()
    assert (triggers / "events.py").is_file()
    assert (triggers / "ui.py").is_file()
    assert "TriggerSpec" in (triggers / "slash.py").read_text(encoding="utf-8")


def test_features_widgets_are_yaml_and_presenters_only() -> None:
    widgets = Path(bot.__file__).resolve().parent / "features" / "widgets"
    assert (widgets / "templates").is_dir()
    assert list((widgets / "templates" / "views").glob("*.yaml"))
    py_files = [path for path in widgets.rglob("*.py") if path.name != "__init__.py"]
    assert {path.name for path in py_files} == {"presenters.py"}
    for path in py_files:
        source = path.read_text(encoding="utf-8")
        assert "discord.ui.View" not in source
        assert "discord.ui.Modal" not in source


def test_app_owns_declarative_widget_engine() -> None:
    widgets = Path(bot.__file__).resolve().parent / "app" / "widgets"
    assert (widgets / "engine.py").is_file()
    assert (widgets / "registry.py").is_file()
    assert "DeclarativeView" in (widgets / "engine.py").read_text(encoding="utf-8")


def test_legacy_packages_are_removed() -> None:
    package = Path(bot.__file__).resolve().parent
    for retired in ("cogs", "messages", "presentation", "recipes", "ui"):
        assert not list((package / retired).glob("*.py"))
    assert not (package / "core" / "layout").exists()
    assert not (package / "core" / "stickies").exists()
    assert not (package / "core" / "integrations").exists()


def test_test_core_is_not_imported_by_production_code() -> None:
    offenders: list[str] = []
    package = Path(bot.__file__).resolve().parent
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "tests.core" in source or "bot.smoke" in source:
            offenders.append(str(path.relative_to(package.parent)))
    assert offenders == []


def test_client_deletion_is_reachable_only_from_delete_recipe_module() -> None:
    package = Path(bot.__file__).resolve().parent
    repository_callers: list[str] = []
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(package.parent))
        if (
            "client_repo.delete_with_relations(" in source
            or "clients.delete_with_relations(" in source
        ):
            repository_callers.append(relative)
    assert repository_callers == ["bot/features/recipes/hub/clients/deletion.py"]
    assert "ClientDeletionService" not in (
        package / "features" / "recipes" / "hub" / "clients" / "deletion.py"
    ).read_text(encoding="utf-8")


def test_test_tree_separates_unit_and_live_code() -> None:
    tests_root = Path(__file__).resolve().parents[1]
    root_python = sorted(path.name for path in tests_root.glob("*.py"))
    assert root_python == ["__init__.py"]
    assert list((tests_root / "unit").glob("test_*.py"))
    assert list((tests_root / "core").glob("*.py"))
    assert not list((tests_root / "live").glob("*.py"))


def test_live_orchestration_is_recipe_driven() -> None:
    tests_root = Path(__file__).resolve().parents[1]
    live_root = tests_root / "live"
    assert not (tests_root / "core" / "suite.py").exists()
    assert list((tests_root / "recipes").glob("*.yaml"))
    assert (tests_root / "core" / "runner.py").exists()
    launcher = (live_root / "smoke_server_init.sh").read_text(encoding="utf-8")
    assert "tests.core.runner recipe" in launcher
    assert "discord" not in launcher.casefold()


def test_features_own_recipes_and_declarative_content() -> None:
    package = Path(bot.__file__).resolve().parent
    features = package / "features"
    assert list(features.rglob("*.yaml"))
    assert list((features / "recipes").rglob("*.py"))
    assert list((features / "widgets").rglob("*.yaml"))
    assert not list((package / "widgets").rglob("*.py"))
    assert not list((package / "widgets").rglob("*.yaml"))
    assert not list((package / "channels").rglob("*.py"))
    assert not list((package / "channels").rglob("*.yaml"))
    assert not list((package / "changelog").rglob("*.yaml"))
    assert not list((package / "adapters").rglob("*.py"))


def test_app_is_generic_and_core_has_no_feature_vocabulary() -> None:
    package = Path(bot.__file__).resolve().parent
    forbidden = (
        "join_requests",
        "network_announcements",
        "leaders_channel",
        "hub_rules",
        "server.init",
    )
    offenders: list[str] = []
    triggers_root = package / "app" / "triggers"
    for root in (package / "app", package / "core"):
        for path in root.rglob("*.py"):
            # Entry catalog intentionally lists product trigger ids.
            try:
                path.relative_to(triggers_root)
            except ValueError:
                pass
            else:
                continue
            source = path.read_text(encoding="utf-8")
            if any(value in source for value in forbidden):
                offenders.append(str(path.relative_to(package.parent)))
    assert offenders == []
    for path in (package / "core" / "triggers").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "server.init" not in source
        assert "request.submit" not in source



def test_hub_initialize_uses_install_recipe_not_direct_stickies() -> None:
    initialize = (
        Path(bot.__file__).resolve().parent / "features" / "recipes" / "hub" / "initialize.py"
    ).read_text(encoding="utf-8")
    index = (
        Path(bot.__file__).resolve().parent / "features" / "recipes" / "recipes.py"
    ).read_text(encoding="utf-8")
    assert "from bot.features.channels.stickies" not in initialize
    assert "clients.reconnect" in initialize
    assert "hub.ensure_installs" in initialize
    assert "hub.migrate" in initialize
    assert "_compose_lifecycle_recipe" in initialize
    assert 'run(\n        "hub.initialize"' in index or 'run("hub.initialize"' in index
    assert '@recipe("hub.migrate")' not in index


def test_widget_presenters_do_not_import_hub_process_modules() -> None:
    presenters = (
        Path(bot.__file__).resolve().parent / "features" / "widgets" / "presenters.py"
    )
    forbidden = (
        "bot.features.recipes.hub.clients",
        "bot.features.recipes.hub.onboarding",
        "bot.features.recipes.hub.network",
        "bot.features.recipes.hub.installs",
        "bot.features.recipes.hub.migrate",
        "bot.features.recipes.hub.relay",
    )
    source = presenters.read_text(encoding="utf-8")
    hits = [name for name in forbidden if name in source]
    assert hits == []

def test_only_generic_feature_loader_imports_feature_package_from_app() -> None:
    package = Path(bot.__file__).resolve().parent
    offenders: list[str] = []
    allowed = package / "app" / "features" / "loader.py"
    for path in (package / "app").rglob("*.py"):
        if path == allowed:
            continue
        imports = _imports_forbidden_layer(
            path.read_text(encoding="utf-8"),
            ("bot.features",),
        )
        if imports:
            offenders.append(f"{path.relative_to(package.parent)}: {', '.join(imports)}")
    assert offenders == []
