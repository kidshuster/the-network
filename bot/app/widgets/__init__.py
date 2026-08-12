"""Generic Discord widget rendering and interaction dispatch."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import discord

from bot.app.widgets.drafts import modal as modal_draft
from bot.app.widgets.drafts import view as view_draft
from bot.app.widgets.errors import TemplateRenderError
from bot.app.widgets.loader import clear_widget_cache, validate_widget_templates
from bot.app.widgets.registry import PersistentViewRegistry
from bot.contracts.widgets import (
    ButtonSpec,
    DismissMessage,
    OpenEphemeralView,
    OpenModal,
    RecipeHandler,
    SelectOptionSpec,
    SelectSpec,
    recipe_handler,
)
from bot.core.templates import render_embed as embed
from bot.core.templates import render_text as text


def message(
    template_id: str,
    *,
    values: Mapping[str, Any] | None = None,
    view: discord.ui.View | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"embed": embed(template_id, **dict(values or {}))}
    if view is not None:
        payload["view"] = view
    return payload

def render_view(name: str, bot: Any, **context: Any) -> Any:
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
    "ButtonSpec", "DismissMessage", "OpenEphemeralView", "OpenModal",
    "PersistentViewRegistry", "RecipeHandler", "SelectOptionSpec", "SelectSpec",
    "TemplateRenderError", "clear_widget_cache", "embed", "message", "modal_draft",
    "recipe_handler", "render_modal", "render_view", "text", "validate_widget_templates",
    "view_draft",
]
