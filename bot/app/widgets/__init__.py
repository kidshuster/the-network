"""Generic Discord widget rendering and interaction dispatch."""

from __future__ import annotations

from typing import Any

from bot.app.widgets import renderer
from bot.app.widgets.errors import TemplateRenderError
from bot.app.widgets.loader import clear_widget_cache, validate_widget_templates
from bot.app.widgets.models import ActionBinding, ButtonSpec, SelectOptionSpec, SelectSpec
from bot.app.widgets.registry import PersistentViewRegistry

embed = renderer.embed
text = renderer.text
message = renderer.message
view = renderer.view
modal = renderer.modal


def render_view(name: str, bot: Any, **context: Any) -> Any:
    """Compatibility entry; delegates named composition to features via the bot."""
    return bot.render_named_view(name, **context)


def render_modal(
    name: str,
    bot: Any,
    *,
    params: dict[str, Any] | None = None,
    field_defaults: dict[str, str] | None = None,
) -> Any:
    return bot.render_named_modal(name, params=params, field_defaults=field_defaults)


__all__ = [
    "ActionBinding",
    "ButtonSpec",
    "PersistentViewRegistry",
    "SelectOptionSpec",
    "SelectSpec",
    "TemplateRenderError",
    "clear_widget_cache",
    "embed",
    "message",
    "modal",
    "render_modal",
    "render_view",
    "text",
    "validate_widget_templates",
    "view",
]
