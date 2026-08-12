from __future__ import annotations

from typing import Any

import discord

from bot.app.discord.errors import respond_to_error
from bot.app.discord.responses import DeferredResponse, defer_ephemeral
from bot.app.widgets.errors import TemplateRenderError
from bot.contracts.widgets import (
    DismissMessage,
    OpenEphemeralView,
    OpenModal,
    RecipeHandler,
)
from bot.errors import UserFacingError

# Must keep the interaction undeferred so ``response.send_modal`` can run.
_MODAL_OPEN_RECIPES = frozenset(
    {
        "request.join.open",
        "network.create.open",
        "network.delete.open",
        "client.edit.open",
    }
)


class RenderedView(discord.ui.View):
    def __init__(self, bot: Any, *, timeout: float | None, template_id: str) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.template_id = template_id
        self.decision: dict[str, Any] | None = None
        self.resolutions: dict[str, int] = {}
        self.required_keys: set[str] = set()
        self.candidates: dict[str, set[int]] = {}


class RenderedModal(discord.ui.Modal):
    def __init__(
        self,
        bot: Any,
        *,
        title: str,
        submit: RecipeHandler,
        template_id: str,
    ) -> None:
        super().__init__(title=title)
        self.bot = bot
        self.submit = submit
        self.template_id = template_id
        self.field_ids: list[str] = []
        self.file_fields: set[str] = set()
        self._labels: dict[str, discord.ui.Label[Any]] = {}

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values: dict[str, Any] = {}
        for field_id in self.field_ids:
            label = self._labels.get(field_id)
            if label is None:
                continue
            component = label.component
            if field_id in self.file_fields:
                attachments = list(getattr(component, "values", []) or [])
                values[field_id] = attachments[0] if attachments else None
            elif isinstance(component, discord.ui.TextInput):
                values[field_id] = component.value.strip()
        await handle_handler(self.bot, interaction, self.submit, submitted=values)


async def handle_handler(
    bot: Any,
    interaction: discord.Interaction,
    handler: RecipeHandler,
    *,
    submitted: dict[str, Any] | None = None,
) -> None:
    response: DeferredResponse | None = None
    if handler.recipe not in _MODAL_OPEN_RECIPES:
        if interaction.response.is_done():
            response = DeferredResponse(interaction, ephemeral=True)
        else:
            response = await defer_ephemeral(interaction)

    try:
        payload = _interaction_payload(interaction, handler, submitted)
        result = await bot.recipe_registry.run(handler.recipe, **payload)
    except Exception as error:
        await _handle_error(bot, interaction, error, handler.recipe, response=response)
        return

    if isinstance(result, DismissMessage):
        await _dismiss(interaction, result.content)
        return
    if isinstance(result, OpenModal):
        await _open_modal(bot, interaction, result)
        return
    if isinstance(result, OpenEphemeralView):
        await _open_ephemeral_view(bot, interaction, result)
        return
    if result is None:
        return

    if response is None:
        if interaction.response.is_done():
            response = DeferredResponse(interaction, ephemeral=True)
        else:
            response = await defer_ephemeral(interaction)
    try:
        await _present(bot, interaction, response, handler.recipe, result)
    except Exception as error:
        await _handle_error(bot, interaction, error, handler.recipe, response=response)


async def _dismiss(interaction: discord.Interaction, content: str) -> None:
    if interaction.message is not None:
        try:
            await interaction.message.edit(content=content, view=None)
            return
        except discord.HTTPException:
            pass
    if not interaction.response.is_done():
        await interaction.response.send_message(content, ephemeral=True)
        return
    await interaction.followup.send(content, ephemeral=True)


async def _open_modal(bot: Any, interaction: discord.Interaction, spec: OpenModal) -> None:
    draft = bot.templates_modal(spec.template_id, **dict(spec.values))
    if spec.defaults:
        draft.defaults(**dict(spec.defaults))
    draft.on_submit(spec.submit)
    built = draft.build(bot)
    if interaction.response.is_done():
        await interaction.followup.send("Open the modal from a fresh click.", ephemeral=True)
    else:
        await interaction.response.send_modal(built)


async def _open_ephemeral_view(
    bot: Any,
    interaction: discord.Interaction,
    spec: OpenEphemeralView,
) -> None:
    draft = bot.templates_view(spec.template_id, **dict(spec.values))
    for tag, bound in spec.bindings.items():
        draft.bind(tag, bound)
    for slot, items in spec.slots.items():
        draft.fill(slot, items)
    kwargs: dict[str, Any] = {"view": draft.build(bot), "ephemeral": True}
    if spec.content is not None:
        kwargs["content"] = spec.content
    send = (
        interaction.followup.send
        if interaction.response.is_done()
        else interaction.response.send_message
    )
    await send(**kwargs)


async def _handle_error(
    bot: Any,
    interaction: discord.Interaction,
    error: BaseException,
    operation: str,
    *,
    response: Any = None,
) -> None:
    public: BaseException | None = error
    while public is not None and not isinstance(public, UserFacingError):
        public = public.__cause__
    if isinstance(public, UserFacingError):
        if response is not None:
            await response.send(content=public.message)
            return
        if not interaction.response.is_done():
            await interaction.response.send_message(public.message, ephemeral=True)
            return
        await DeferredResponse(interaction, ephemeral=True).send(content=public.message)
        return
    if response is None:
        if interaction.response.is_done():
            response = DeferredResponse(interaction, ephemeral=True)
        else:
            response = await defer_ephemeral(interaction)
    await respond_to_error(bot, interaction, response, error, operation=operation)


def _interaction_payload(
    interaction: discord.Interaction,
    handler: RecipeHandler,
    submitted: dict[str, Any] | None,
) -> dict[str, Any]:
    persistent = dict(handler.arguments)
    runtime = dict(submitted or {})
    overlap = sorted(set(persistent) & set(runtime))
    if overlap:
        raise TemplateRenderError(
            f"submitted keys collide with persistent handler arguments: {overlap}",
            template_id=handler.recipe,
            element_id=overlap[0],
        )
    return {**persistent, **runtime, "interaction": interaction}


async def _present(
    bot: Any,
    interaction: discord.Interaction,
    response: Any,
    recipe: str,
    result: Any,
) -> None:
    presenter = f"present.{recipe}"
    if bot.recipe_registry.has(presenter):
        await bot.recipe_registry.run(
            presenter,
            response=response,
            value=result,
            interaction=interaction,
        )
        return
    if getattr(result, "success", None) is False:
        from bot.app.discord.errors import respond_with_error

        await respond_with_error(
            bot,
            interaction,
            response,
            getattr(result, "error", None) or "Request failed",
            operation=recipe,
            title="Request Failed",
        )
        return
    if getattr(response, "sent", False):
        return
    await response.send(content="Done.")
