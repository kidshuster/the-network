from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from bot.app.widgets.schema import ViewTemplateSpec

_BOT_DIR = Path(__file__).resolve().parents[2]
_TEMPLATES_DIR = _BOT_DIR / "features" / "widgets" / "templates"
_VIEWS_DIR = _TEMPLATES_DIR / "views"
_MODALS_DIR = _TEMPLATES_DIR / "modals"

_cache: dict[str, ViewTemplateSpec] = {}
_modal_meta_cache: dict[str, dict[str, Any]] = {}

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_\.]*)\}")


class WidgetTemplateError(Exception):
    pass


def clear_widget_cache() -> None:
    _cache.clear()
    _modal_meta_cache.clear()


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise WidgetTemplateError(f"{path.name}: expected mapping at root")
    return raw


def load_view_spec(name: str) -> ViewTemplateSpec:
    if name in _cache:
        return _cache[name]
    path = _VIEWS_DIR / f"{name}.yaml"
    if not path.is_file():
        raise WidgetTemplateError(f"View template not found: {name}")
    raw = _load_yaml(path)
    try:
        spec = ViewTemplateSpec.model_validate(raw)
    except ValidationError as exc:
        raise WidgetTemplateError(f"{path.name}: {exc}") from exc
    if spec.id != name and spec.id != raw.get("id"):
        pass
    _cache[name] = spec
    return spec


def load_modal_meta(name: str) -> dict[str, Any]:
    """Extra modal keys (require/inject/on_success) not on ModalTemplateSpec."""
    if name in _modal_meta_cache:
        return _modal_meta_cache[name]
    path = _MODALS_DIR / f"{name}.yaml"
    if not path.is_file():
        raise WidgetTemplateError(f"Modal template not found: {name}")
    raw = _load_yaml(path)
    meta = {
        "require": raw.get("require") or [],
        "inject": raw.get("inject") or [],
        "on_success": raw.get("on_success"),
        "on_error": raw.get("on_error"),
        "field_defaults": raw.get("field_defaults") or {},
        "field_map": raw.get("field_map") or {},
        "params": raw.get("params") or {},
    }
    _modal_meta_cache[name] = meta
    return meta


def substitute(text: str, ctx: dict[str, Any]) -> str:
    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        value = _resolve_path(ctx, key)
        if value is None:
            return match.group(0)
        return str(value)

    return _PLACEHOLDER_RE.sub(replacer, text)


def _resolve_path(ctx: dict[str, Any], path: str) -> Any:
    current: Any = ctx
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            if not hasattr(current, part):
                return None
            current = getattr(current, part)
    return current


def resolve_path(ctx: dict[str, Any], path: str) -> Any:
    return _resolve_path(ctx, path)


def truthy(expr: str | None, ctx: dict[str, Any]) -> bool:
    if expr is None:
        return False
    # Support simple paths and "not path"
    text = expr.strip()
    negate = False
    if text.startswith("!"):
        negate = True
        text = text[1:].strip()
    elif text.startswith("not "):
        negate = True
        text = text[4:].strip()
    value = _resolve_path(ctx, text)
    if isinstance(value, str):
        value = value.strip()
        result = bool(value) and value not in ("0", "False", "false")
    else:
        result = bool(value)
    return (not result) if negate else result


def map_context(mapping: dict[str, str], *, result: Any, params: dict[str, Any]) -> dict[str, Any]:
    ctx: dict[str, Any] = {"result": result, "params": params, **params}
    if result is not None and hasattr(result, "__dict__"):
        ctx.update(vars(result) if hasattr(result, "__dict__") else {})
    out: dict[str, Any] = {}
    for key, path in mapping.items():
        value = _resolve_path(ctx, path)
        if value is None and path.startswith("result."):
            value = _resolve_path({"result": result}, path)
        out[key] = "" if value is None else value
    return out


def validate_widget_templates() -> None:
    errors: list[str] = []
    if _VIEWS_DIR.is_dir():
        for path in sorted(_VIEWS_DIR.glob("*.yaml")):
            try:
                _cache.pop(path.stem, None)
                load_view_spec(path.stem)
            except WidgetTemplateError as exc:
                errors.append(str(exc))
    if errors:
        raise WidgetTemplateError("Invalid widget templates:\n" + "\n".join(errors))
