from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.app.widgets.dispatch import handle_handler
from bot.contracts.widgets import OpenModal, recipe_handler


@pytest.mark.asyncio
async def test_handle_handler_defers_before_recipe_run() -> None:
    order: list[str] = []

    async def _defer(*, ephemeral: bool = True) -> None:
        del ephemeral
        order.append("defer")

    async def _run(recipe: str, **_: object) -> SimpleNamespace:
        order.append(f"run:{recipe}")
        return SimpleNamespace(success=True)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.response.defer = AsyncMock(side_effect=_defer)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    bot = MagicMock()
    bot.recipe_registry.run = AsyncMock(side_effect=_run)
    bot.recipe_registry.has = MagicMock(return_value=False)

    await handle_handler(bot, interaction, recipe_handler("request.approve", request_id=1))

    assert order[0] == "defer"
    assert order[1] == "run:request.approve"
    interaction.response.defer.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_handler_skips_early_defer_for_modal_open() -> None:
    async def _run(recipe: str, **_: object) -> OpenModal:
        del recipe
        return OpenModal(
            template_id="join_network",
            submit=recipe_handler("request.submit"),
        )

    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.response.defer = AsyncMock()
    interaction.response.send_modal = AsyncMock()

    modal = MagicMock()
    draft = MagicMock()
    draft.build = MagicMock(return_value=modal)
    draft.defaults = MagicMock(return_value=draft)
    draft.on_submit = MagicMock(return_value=draft)

    bot = MagicMock()
    bot.recipe_registry.run = AsyncMock(side_effect=_run)
    bot.templates_modal = MagicMock(return_value=draft)

    await handle_handler(bot, interaction, recipe_handler("request.join.open"))

    interaction.response.defer.assert_not_awaited()
    interaction.response.send_modal.assert_awaited_once_with(modal)
