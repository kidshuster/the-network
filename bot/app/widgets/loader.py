from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from bot.app.widgets.errors import TemplateRenderError
from bot.app.widgets.schema import ModalTemplateSpec, ViewTemplateSpec, reject_forbidden

_BOT_DIR = Path(__file__).resolve().parents[2]
_TEMPLATES_DIR = _BOT_DIR / "features" / "widgets" / "templates"
_VIEWS_DIR = _TEMPLATES_DIR / "views"
_MODALS_DIR = _TEMPLATES_DIR / "modals"
_view_cache: dict[str, ViewTemplateSpec] = {}
_modal_cache: dict[str, ModalTemplateSpec] = {}


def clear_widget_cache() -> None:
    _view_cache.clear()
    _modal_cache.clear()


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TemplateRenderError(f"{path.name}: expected mapping at root")
    return raw


def load_view(template_id: str) -> ViewTemplateSpec:
    if template_id in _view_cache:
        return _view_cache[template_id]
    path = _VIEWS_DIR / f"{template_id}.yaml"
    if not path.is_file():
        raise TemplateRenderError("view template not found", template_id=template_id)
    raw = _load_yaml(path)
    try:
        spec = ViewTemplateSpec.model_validate(raw)
    except (ValidationError, ValueError) as exc:
        raise TemplateRenderError(str(exc), template_id=template_id) from exc
    if spec.id != template_id:
        raise TemplateRenderError(
            f"template id {spec.id!r} does not match file stem",
            template_id=template_id,
        )
    _view_cache[template_id] = spec
    return spec


def load_modal(template_id: str) -> ModalTemplateSpec:
    if template_id in _modal_cache:
        return _modal_cache[template_id]
    path = _MODALS_DIR / f"{template_id}.yaml"
    if not path.is_file():
        raise TemplateRenderError("modal template not found", template_id=template_id)
    raw = _load_yaml(path)
    if raw.get("id") is None:
        raw = {**raw, "id": template_id}
    try:
        reject_forbidden(raw, where="modal")
        spec = ModalTemplateSpec.model_validate(raw)
    except (ValidationError, ValueError) as exc:
        raise TemplateRenderError(str(exc), template_id=template_id) from exc
    _modal_cache[template_id] = spec
    return spec


def validate_widget_templates() -> None:
    errors: list[str] = []
    clear_widget_cache()
    for path in sorted(_VIEWS_DIR.glob("*.yaml")):
        try:
            load_view(path.stem)
        except TemplateRenderError as exc:
            errors.append(str(exc))
    for path in sorted(_MODALS_DIR.glob("*.yaml")):
        try:
            load_modal(path.stem)
        except TemplateRenderError as exc:
            errors.append(str(exc))
    if errors:
        raise TemplateRenderError("Invalid widget templates:\n" + "\n".join(errors))
