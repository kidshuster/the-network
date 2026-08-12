from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock


def wire_widget_bot(bot: MagicMock | None = None) -> MagicMock:
    """Attach draft/template hooks used by NetworkRelayBot."""
    from bot.app.features import build_recipe_registry
    from bot.app.widgets.drafts import modal as modal_draft
    from bot.app.widgets.drafts import view as view_draft
    from bot.features.widgets.builders import build_named_modal, build_named_view

    bot = bot or MagicMock()
    bot.templates_view = lambda template_id, **values: view_draft(template_id, **values)
    bot.templates_modal = lambda template_id, **values: modal_draft(template_id, **values)
    bot.render_named_view = lambda name, **kwargs: build_named_view(bot, name, **kwargs)
    bot.render_named_modal = lambda name, **kwargs: build_named_modal(bot, name, **kwargs)
    bot.render_view = lambda name, **kwargs: bot.render_named_view(name, **kwargs)
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


def mock_recipe_result(
    bot: MagicMock,
    *,
    recipe: str,
    result: Any,
) -> None:
    """Run real presenters; return a stub for one action recipe."""
    real_run = bot.recipe_registry.run

    async def _run(name: str, **kwargs: Any) -> Any:
        if name == recipe:
            if getattr(result, "success", None) is False:
                from bot.errors import UserFacingError

                raise UserFacingError(
                    str(getattr(result, "error", None) or "Request failed"),
                    title="Request Failed",
                )
            return result
        return await real_run(name, **kwargs)

    bot.recipe_registry.run = _run  # type: ignore[method-assign]
