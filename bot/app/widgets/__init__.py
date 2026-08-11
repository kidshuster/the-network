"""Declarative Discord UI renderer (YAML views/modals → triggers)."""

from __future__ import annotations

from bot.app.widgets.engine import render_modal, render_view
from bot.app.widgets.loader import clear_widget_cache, validate_widget_templates
from bot.app.widgets.registry import PersistentViewRegistry

__all__ = [
    "PersistentViewRegistry",
    "clear_widget_cache",
    "render_modal",
    "render_view",
    "validate_widget_templates",
]
