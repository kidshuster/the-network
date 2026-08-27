"""Inventory: every persistent button/select handler is a registered UI recipe.

Smoke never clicked Discord components, so Blacklist regressions slipped through.
This gate fails when a builder binds an unregistered recipe or a UI entry is missing
from the trigger catalog.
"""

from __future__ import annotations

from typing import Any

import discord
import pytest
from widget_helpers import wire_widget_bot

from bot.app.triggers import build_trigger_catalog
from bot.app.widgets import custom_id, render_view
from bot.core.triggers import TriggerKind
from bot.features.widgets.builders import build_named_view

_UI_KINDS = {TriggerKind.BUTTON, TriggerKind.SELECT, TriggerKind.MODAL}

# Representative contexts that exercise every dynamic slot/button set.
_VIEW_CONTEXTS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("join_network", {}),
    ("network_admin", {}),
    ("moderator_review", {"request_id": 1}),
    ("subscribe_setup", {"subscription_id": 3, "network_key": "stingers"}),
    ("delete_client_confirm", {"client_id": 1}),
    (
        "network_profile",
        {
            "client_id": 1,
            "network_keys": ["stingers", "smoke"],
            "subscribed_keys": {"stingers"},
            "timecode_enabled": False,
            "read_only": False,
        },
    ),
    (
        "subscription_moderation",
        {
            "subscription_id": 3,
            "network_key": "stingers",
            "show_subscribe_connected": True,
            "show_blacklist": True,
        },
    ),
    (
        "subscription_moderation",
        {
            "subscription_id": 3,
            "network_key": "stingers",
            "show_subscribe_connected": False,
            "show_blacklist": True,
        },
    ),
)


def _handlers_from_view(view: discord.ui.View) -> set[str]:
    recipes: set[str] = set()
    for child in view.children:
        custom = getattr(child, "custom_id", None)
        if not custom:
            continue
        handler = custom_id.decode(custom)
        recipes.add(handler.recipe)
    return recipes


def test_named_views_bind_only_registered_ui_recipes() -> None:
    bot = wire_widget_bot()
    catalog = build_trigger_catalog()
    seen: set[str] = set()

    for name, ctx in _VIEW_CONTEXTS:
        view = build_named_view(bot, name, **ctx)
        recipes = _handlers_from_view(view)
        assert recipes, f"{name} produced no interactable components"
        for recipe in recipes:
            assert bot.recipe_registry.has(recipe), f"{name}: unregistered recipe {recipe!r}"
            if recipe.startswith("test."):
                continue
            assert recipe in catalog.ids(), f"{name}: {recipe!r} missing from UI trigger catalog"
            assert catalog.get(recipe).kind in _UI_KINDS, (
                f"{name}: {recipe!r} trigger kind must be button/select/modal"
            )
        seen |= recipes

    # Blacklist open is the regression that previously had no catalog entry / no click path.
    assert "subscription.blacklist.open" in seen


def test_blacklist_replace_is_catalogued_as_select() -> None:
    catalog = build_trigger_catalog()
    assert catalog.get("blacklist.replace").kind is TriggerKind.SELECT
    assert catalog.get("subscription.blacklist.open").kind is TriggerKind.BUTTON


@pytest.mark.asyncio
async def test_subscription_moderation_blacklist_control_is_clickable() -> None:
    """Smoke substitute: the Blacklist control must be present and dispatchable."""
    bot = wire_widget_bot()
    view = render_view(
        "subscription_moderation",
        bot,
        subscription_id=3,
        network_key="stingers",
        show_blacklist=True,
    )
    blacklist = next(
        (
            child
            for child in view.children
            if isinstance(child, discord.ui.Button) and child.label == "Blacklist"
        ),
        None,
    )
    assert blacklist is not None
    handler = custom_id.decode(blacklist.custom_id or "")
    assert handler.recipe == "subscription.blacklist.open"
    assert handler.arguments.get("subscription_id") == 3
