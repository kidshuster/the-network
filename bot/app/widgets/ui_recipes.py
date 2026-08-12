"""App-owned built-in UI recipes registered like every other recipe."""

from __future__ import annotations

import discord

from bot.app.widgets.dispatch import RenderedView
from bot.contracts.recipes import RecipeContext, recipe
from bot.contracts.widgets import DismissMessage
from bot.errors import UserFacingError


@recipe("ui.dismiss")
async def dismiss_message(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> DismissMessage:
    del recipe_context, interaction
    return DismissMessage()


async def _reply_ephemeral(interaction: discord.Interaction, content: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)


@recipe("ui.migrate.cancel")
async def migrate_cancel(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> None:
    del recipe_context
    view = getattr(interaction, "view", None)
    if isinstance(view, RenderedView):
        view.decision = None
        view.stop()
    if not interaction.response.is_done():
        await interaction.response.defer()


@recipe("ui.migrate.confirm")
async def migrate_confirm(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> None:
    del recipe_context
    view = getattr(interaction, "view", None)
    if not isinstance(view, RenderedView):
        if not interaction.response.is_done():
            await interaction.response.defer()
        return
    missing = sorted(view.required_keys - set(view.resolutions))
    invalid = sorted(
        key
        for key, value in view.resolutions.items()
        if key not in view.candidates or value not in view.candidates[key]
    )
    if missing or invalid:
        parts: list[str] = []
        if missing:
            parts.append("unresolved: " + ", ".join(f"`{key}`" for key in missing))
        if invalid:
            parts.append("invalid: " + ", ".join(f"`{key}`" for key in invalid))
        await _reply_ephemeral(
            interaction,
            "Migration review is incomplete — " + "; ".join(parts) + ".",
        )
        return
    view.decision = {"ok": True}
    view.stop()
    if not interaction.response.is_done():
        await interaction.response.defer()


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
    if not isinstance(view, RenderedView):
        if not interaction.response.is_done():
            await interaction.response.defer()
        return
    if resource_key not in view.required_keys:
        raise UserFacingError(
            f"Unexpected migration resource `{resource_key}`.",
            code="migration_unexpected_resource",
        )
    if not values:
        raise UserFacingError(
            f"Select a channel for `{resource_key}`.",
            code="migration_selection_required",
        )
    try:
        chosen = int(values[0])
    except (TypeError, ValueError) as exc:
        raise UserFacingError(
            f"Invalid channel selection for `{resource_key}`.",
            code="migration_invalid_selection",
        ) from exc
    allowed = view.candidates.get(resource_key, set())
    if chosen not in allowed:
        raise UserFacingError(
            f"Selected channel is not a candidate for `{resource_key}`.",
            code="migration_invalid_candidate",
        )
    view.resolutions[resource_key] = chosen
    if not interaction.response.is_done():
        await interaction.response.defer()
