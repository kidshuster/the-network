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


def test_features_do_not_import_app_runtime() -> None:
    package = Path(bot.__file__).resolve().parent / "features"
    offenders: list[str] = []
    for path in package.rglob("*.py"):
        rel = path.relative_to(Path(bot.__file__).resolve().parent.parent)
        imports = _imports_forbidden_layer(
            path.read_text(encoding="utf-8"),
            ("bot.app",),
        )
        if imports:
            offenders.append(f"{rel}: {', '.join(imports)}")
    assert offenders == [], "features -> app violations:\n" + "\n".join(offenders)


def test_permission_mutations_only_in_core_permissions_service() -> None:
    package = Path(bot.__file__).resolve().parent
    allowed = package / "core" / "permissions" / "service.py"
    offenders: list[str] = []
    for path in package.rglob("*.py"):
        if path.resolve() == allowed.resolve():
            continue
        source = path.read_text(encoding="utf-8")
        if "set_permissions(" in source or ".edit(overwrites=" in source:
            offenders.append(str(path.relative_to(package.parent)))
    assert offenders == [], "direct permission mutations:\n" + "\n".join(offenders)


def test_feature_layout_lives_under_features_channels() -> None:
    package = Path(bot.__file__).resolve().parent
    assert not (package / "app" / "layout").exists()
    layout = package / "features" / "channels" / "layout"
    assert (layout / "layout.yaml").is_file()
    assert (layout / "compiler.py").is_file()
    assert (layout / "managed.py").is_file()
    assert (layout / "loader.py").is_file()


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


def test_features_widgets_have_no_discord_ui_subclasses() -> None:
    widgets = Path(bot.__file__).resolve().parent / "features" / "widgets"
    assert (widgets / "templates").is_dir()
    assert list((widgets / "templates" / "views").glob("*.yaml"))
    for path in widgets.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "discord.ui.View" not in source
        assert "discord.ui.Modal" not in source


def test_app_owns_widget_drafts_not_interpreter() -> None:
    widgets = Path(bot.__file__).resolve().parent / "app" / "widgets"
    assert (widgets / "drafts.py").is_file()
    assert (widgets / "registry.py").is_file()
    assert not (widgets / "engine.py").exists()
    assert not (widgets / "policies.py").exists()
    assert not (widgets / "renderer.py").exists()
    assert "RenderedView" in (widgets / "dispatch.py").read_text(encoding="utf-8")
    assert "ViewDraft" in (widgets / "drafts.py").read_text(encoding="utf-8")


def test_presentation_templates_forbid_executable_keys() -> None:
    import yaml

    forbidden = {
        "require",
        "inject",
        "store",
        "finish",
        "on_success",
        "on_error",
        "field_map",
        "options_from",
        "foreach",
        "when",
        "disabled_when",
        "trigger",
        "action",
        "recipe",
        "handler",
        "authorize",
        "custom_id",
    }
    root = Path(bot.__file__).resolve().parent / "features" / "widgets" / "templates"
    offenders: list[str] = []

    def walk(obj: object, path: str) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in forbidden:
                    offenders.append(f"{path}:{key}")
                walk(value, path)
        elif isinstance(obj, list):
            for value in obj:
                walk(value, path)

    for file_path in root.rglob("*.yaml"):
        walk(yaml.safe_load(file_path.read_text()), str(file_path))
    assert offenders == []


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
        # Test-only Discord adapter may load tests via importlib when enabled.
        if "app/testing" in str(path.as_posix()):
            continue
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
    server = (
        Path(bot.__file__).resolve().parent / "features" / "recipes" / "server.py"
    ).read_text(encoding="utf-8")
    assert "from bot.features.channels.stickies" not in initialize
    assert "clients.reconnect" in initialize
    assert "hub.ensure_installs" in initialize
    assert "hub.migrate" in initialize
    assert "_compose_lifecycle_recipe" in initialize
    assert 'run(\n        "hub.initialize"' in server or 'run("hub.initialize"' in server
    assert '@recipe("hub.migrate")' not in server


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

def test_only_composition_roots_import_feature_package_from_app() -> None:
    package = Path(bot.__file__).resolve().parent
    offenders: list[str] = []
    allowed = {
        (package / "app" / "features" / "loader.py").resolve(),
        (package / "app" / "bot.py").resolve(),
    }
    testing_root = (package / "app" / "testing").resolve()
    for path in (package / "app").rglob("*.py"):
        if path.resolve() in allowed:
            continue
        try:
            path.resolve().relative_to(testing_root)
        except ValueError:
            pass
        else:
            continue
        imports = _imports_forbidden_layer(
            path.read_text(encoding="utf-8"),
            ("bot.features",),
        )
        if imports:
            offenders.append(f"{path.relative_to(package.parent)}: {', '.join(imports)}")
    assert offenders == []


def test_widget_drafts_do_not_import_features_or_repos() -> None:
    widgets = Path(bot.__file__).resolve().parent / "app" / "widgets"
    forbidden = ("bot.features", "bot.core.database", "bot.core.repositories")
    offenders: list[str] = []
    for name in (
        "drafts.py",
        "dispatch.py",
        "loader.py",
        "schema.py",
        "custom_id.py",
    ):
        path = widgets / name
        imports = _imports_forbidden_layer(path.read_text(encoding="utf-8"), forbidden)
        if imports:
            offenders.append(f"{name}: {', '.join(imports)}")
    assert offenders == []


def test_feature_widgets_have_no_enrichment_or_action_maps() -> None:
    widgets = Path(bot.__file__).resolve().parent / "features" / "widgets"
    assert not (widgets / "bindings.py").exists()
    assert not (widgets / "render.py").exists()
    for path in widgets.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "enrich_trigger_payload" not in source
        assert "_MANAGE_ACTIONS" not in source
        assert "_CLIENT_ACTIONS" not in source
