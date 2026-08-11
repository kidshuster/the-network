from __future__ import annotations

from bot.app.triggers import events as event_triggers
from bot.app.triggers import slash as slash_triggers
from bot.app.triggers import ui as ui_triggers
from bot.core.triggers import TriggerCatalog


def build_trigger_catalog() -> TriggerCatalog:
    catalog = TriggerCatalog()
    catalog.register_many(slash_triggers.TRIGGERS)
    catalog.register_many(event_triggers.TRIGGERS)
    catalog.register_many(ui_triggers.TRIGGERS)
    return catalog
