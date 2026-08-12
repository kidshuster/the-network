"""App-owned built-in UI recipes registered like every other recipe."""

from __future__ import annotations

import discord

from bot.app.widgets.dispatch import RenderedView
from bot.contracts.recipes import RecipeContext, recipe
from bot.contracts.widgets import DismissMessage


@recipe("ui.dismiss")
async def dismiss_message(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> DismissMessage:
    del recipe_context, interaction
    return DismissMessage()


async def _migrate_decision(
    interaction: discord.Interaction, *, decision: dict[str, bool] | None
) -> None:
    view = getattr(interaction, "view", None)
    if isinstance(view, RenderedView):
        view.decision = decision
        view.stop()
    if not interaction.response.is_done():
        await interaction.response.defer()


@recipe("ui.migrate.confirm")
async def migrate_confirm(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> None:
    del recipe_context
    await _migrate_decision(interaction, decision={"ok": True})


@recipe("ui.migrate.cancel")
async def migrate_cancel(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> None:
    del recipe_context
    await _migrate_decision(interaction, decision=None)


@recipe("ui.migrate.store")
async def migrate_store(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    resource_key: str,
    select_values: list[str] | tuple[str, ...] | None = None,
    selected_client_ids: list[str] | tuple[str, ...] | None = None,
) -> None:
    del recipe_context, selected_client_ids
    view = getattr(interaction, "view", None)
    values = list(select_values or ())
    if isinstance(view, RenderedView) and resource_key and values:
        view.resolutions[resource_key] = int(values[0])
    if not interaction.response.is_done():
        await interaction.response.defer()
