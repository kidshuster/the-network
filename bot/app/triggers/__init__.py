"""Application entry-point registrations (slash, events, UI triggers)."""

from __future__ import annotations

from bot.app.triggers.catalog import build_trigger_catalog
from bot.core.triggers import TriggerCatalog, dispatch, dispatch_event

__all__ = [
    "TriggerCatalog",
    "build_trigger_catalog",
    "dispatch",
    "dispatch_event",
]
