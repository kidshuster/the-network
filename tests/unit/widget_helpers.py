from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock


def wire_widget_bot(bot: MagicMock | None = None) -> MagicMock:
    """Attach named-view composition hooks used by NetworkRelayBot."""
    from bot.app.features import build_recipe_registry
    from bot.app.widgets import modal as build_modal
    from bot.app.widgets import view as build_view
    from bot.features.widgets.bindings import enrich_trigger_payload
    from bot.features.widgets.render import (
        build_ui_modal,
        build_ui_view,
        render_named_modal,
        render_named_view,
    )

    bot = bot or MagicMock()
    bot.build_widget_view = lambda name, **kwargs: build_view(bot, name, **kwargs)
    bot.build_widget_modal = lambda name, **kwargs: build_modal(bot, name, **kwargs)
    bot.render_named_view = lambda name, **kwargs: render_named_view(bot, name, **kwargs)
    bot.render_named_modal = lambda name, **kwargs: render_named_modal(bot, name, **kwargs)

    async def _build_ui_modal(modal_id: str, args: dict[str, Any], **kwargs: Any) -> Any:
        return await build_ui_modal(bot, modal_id, args, **kwargs)

    async def _build_ui_view(view_id: str, args: dict[str, Any], **kwargs: Any) -> Any:
        return await build_ui_view(bot, view_id, args, **kwargs)

    async def _enrich(action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await enrich_trigger_payload(bot, action, payload)

    bot.build_ui_modal = _build_ui_modal
    bot.build_ui_view = _build_ui_view
    bot.enrich_widget_trigger = _enrich
    bot.make_view_registry = MagicMock(return_value=MagicMock())
    if not isinstance(getattr(bot, "dispatch_trigger", None), AsyncMock):
        bot.dispatch_trigger = AsyncMock()
    bot.recipe_registry = build_recipe_registry(bot)
    return bot


async def click_button(view: Any, label: str, interaction: Any) -> None:
    import discord

    for child in getattr(view, "children", []):
        if isinstance(child, discord.ui.Button) and child.label == label:
            await child.callback(interaction)
            return
    raise AssertionError(f"Button {label!r} not found")
