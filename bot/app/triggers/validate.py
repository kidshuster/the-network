from __future__ import annotations

from pathlib import Path

import yaml

from bot.app.triggers.catalog import build_trigger_catalog
from bot.core.triggers import TriggerCatalog, TriggerCatalogError, TriggerKind

_WIDGET_TEMPLATES = (
    Path(__file__).resolve().parents[2] / "features" / "widgets" / "templates"
)


def _iter_trigger_refs() -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for directory in ("modals", "buttons", "embeds", "popups", "views"):
        root = _WIDGET_TEMPLATES / directory
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                continue
            trigger = data.get("trigger")
            if isinstance(trigger, str) and trigger.strip():
                refs.append((f"{directory}/{path.stem}", trigger.strip()))
            for item in data.get("buttons") or []:
                if isinstance(item, dict):
                    button_trigger = item.get("trigger")
                    if isinstance(button_trigger, str) and button_trigger.strip():
                        button_id = item.get("id", "?")
                        refs.append(
                            (f"{directory}/{path.stem}:{button_id}", button_trigger.strip())
                        )
            for item in data.get("components") or []:
                if not isinstance(item, dict):
                    continue
                action = item.get("action") or {}
                if isinstance(action, dict):
                    action_trigger = action.get("trigger")
                    if isinstance(action_trigger, str) and action_trigger.strip():
                        refs.append(
                            (
                                f"{directory}/{path.stem}:{item.get('id', '?')}",
                                action_trigger.strip(),
                            )
                        )
    return refs


def validate_template_triggers(catalog: TriggerCatalog | None = None) -> None:
    """Fail fast when YAML ``trigger:`` ids are missing from the app catalog."""
    resolved = catalog if catalog is not None else build_trigger_catalog()
    known = resolved.ids()
    ui_kinds = {TriggerKind.BUTTON, TriggerKind.SELECT, TriggerKind.MODAL}
    errors: list[str] = []
    for location, trigger_id in _iter_trigger_refs():
        if trigger_id not in known:
            errors.append(f"{location}: unknown trigger {trigger_id!r}")
            continue
        try:
            spec = resolved.get(trigger_id)
        except TriggerCatalogError as exc:
            errors.append(f"{location}: {exc}")
            continue
        if spec.kind not in ui_kinds:
            errors.append(
                f"{location}: trigger {trigger_id!r} is {spec.kind.value}, "
                f"expected button/select/modal"
            )
    if errors:
        raise TriggerCatalogError("Invalid template triggers:\n" + "\n".join(errors))
