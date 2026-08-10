from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import bot


def _service_python_files() -> list[Path]:
    services_root = Path(bot.__file__).resolve().parent / "services"
    return sorted(services_root.rglob("*.py"))


def _imports_bot_ui(source: str) -> list[str]:
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("bot.ui"):
                violations.append(f"from {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("bot.ui"):
                    violations.append(f"import {alias.name}")
    return violations


def test_service_modules_do_not_import_bot_ui() -> None:
    offenders: list[str] = []
    for path in _service_python_files():
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(Path(bot.__file__).resolve().parent.parent)
        source = path.read_text(encoding="utf-8")
        ui_imports = _imports_bot_ui(source)
        if ui_imports:
            offenders.append(f"{rel}: {', '.join(ui_imports)}")
    assert offenders == [], "service→UI imports:\n" + "\n".join(offenders)


def test_bot_modules_import_cleanly() -> None:
    package = Path(bot.__file__).resolve().parent
    for module in pkgutil.walk_packages([str(package)], prefix="bot."):
        if module.name.startswith("bot.smoke."):
            continue
        importlib.import_module(module.name)
