from __future__ import annotations

from typing import Any

import discord

from bot.app.discord.errors import respond_to_error, respond_with_error
from bot.app.discord.responses import defer_ephemeral
from bot.app.widgets.models import ActionBinding, Primitive


class RenderedView(discord.ui.View):
    def __init__(
        self,
        bot: Any,
        *,
        timeout: float | None,
        template_id: str,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.template_id = template_id
        self.decision: dict[str, Any] | None = None


class RenderedModal(discord.ui.Modal):
    def __init__(
        self,
        bot: Any,
        *,
        title: str,
        submit: ActionBinding,
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
        values: dict[str, Primitive] = {}
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
        arguments = {**dict(self.submit.arguments), **values}
        await handle_binding(
            self.bot,
            interaction,
            ActionBinding(action=self.submit.action, arguments=arguments),
        )


async def handle_binding(
    bot: Any,
    interaction: discord.Interaction,
    binding: ActionBinding,
) -> None:
    action = binding.action
    if action == "ui.dismiss":
        if interaction.message is not None:
            if interaction.response.is_done():
                await interaction.edit_original_response(content="Cancelled.", view=None)
            else:
                await interaction.response.edit_message(content="Cancelled.", view=None)
        elif not interaction.response.is_done():
            await interaction.response.send_message("Cancelled.", ephemeral=True)
        return

    if action in {"ui.migrate.confirm", "ui.migrate.cancel", "ui.migrate.store"}:
        view = getattr(interaction, "view", None)
        if isinstance(view, RenderedView) and action != "ui.migrate.store":
            view.decision = {"ok": True} if action.endswith("confirm") else None
            view.stop()
        if not interaction.response.is_done():
            await interaction.response.defer()
        return

    if action.startswith("ui.modal:"):
        modal_id = action.removeprefix("ui.modal:")
        try:
            built = await bot.build_ui_modal(
                modal_id, dict(binding.arguments), actor=interaction.user
            )
        except Exception as error:
            await _ui_error(bot, interaction, error, action)
            return
        if interaction.response.is_done():
            await interaction.followup.send("Open the modal from a fresh click.", ephemeral=True)
        else:
            await interaction.response.send_modal(built)
        return

    if action.startswith("ui.view:"):
        view_id = action.removeprefix("ui.view:")
        try:
            payload = await bot.build_ui_view(
                view_id,
                dict(binding.arguments),
                actor=interaction.user,
                guild=interaction.guild,
            )
        except Exception as error:
            await _ui_error(bot, interaction, error, action)
            return
        content = payload.get("content")
        child = payload["view"]
        if interaction.response.is_done():
            await interaction.followup.send(content=content, view=child, ephemeral=True)
        else:
            kwargs: dict[str, Any] = {"view": child, "ephemeral": True}
            if content is not None:
                kwargs["content"] = content
            await interaction.response.send_message(**kwargs)
        return

    try:
        payload = await _trigger_payload(bot, interaction, binding)
    except Exception as error:
        await _ui_error(bot, interaction, error, binding.action)
        return

    response = await defer_ephemeral(interaction)
    try:
        result = await bot.dispatch_trigger(binding.action, **payload)
        await _present(bot, interaction, response, binding.action, result)
    except Exception as error:
        await respond_to_error(bot, interaction, response, error, operation=binding.action)


async def _ui_error(
    bot: Any,
    interaction: discord.Interaction,
    error: BaseException,
    operation: str,
) -> None:
    from bot.errors import UserFacingError

    if isinstance(error, UserFacingError) and not interaction.response.is_done():
        await interaction.response.send_message(error.message, ephemeral=True)
        return
    response = await defer_ephemeral(interaction)
    await respond_to_error(bot, interaction, response, error, operation=operation)


async def _trigger_payload(
    bot: Any,
    interaction: discord.Interaction,
    binding: ActionBinding,
) -> dict[str, Any]:
    guild = interaction.guild
    payload: dict[str, Any] = dict(binding.arguments)
    payload["interaction"] = interaction
    if guild is not None:
        payload.setdefault("guild", guild)
        if guild.me is not None:
            payload.setdefault("bot_member", guild.me)
    user = interaction.user
    if isinstance(user, discord.Member) or (
        hasattr(user, "roles") and hasattr(user, "guild_permissions")
    ):
        payload.setdefault("moderator", user)
        payload.setdefault("member", user)
    payload.setdefault("requester", user)
    payload.setdefault("view_registry", bot.make_view_registry())
    enriched: dict[str, Any] = await bot.enrich_widget_trigger(binding.action, payload)
    return enriched


async def _present(
    bot: Any,
    interaction: discord.Interaction,
    response: Any,
    action: str,
    result: Any,
) -> None:
    presenter = f"present.{action}"
    try:
        await bot.recipe_registry.run(
            presenter,
            response=response,
            value=result,
            interaction=interaction,
        )
        return
    except Exception:
        pass
    if getattr(result, "success", None) is False:
        await respond_with_error(
            bot,
            interaction,
            response,
            getattr(result, "error", None) or "Request failed",
            operation=action,
            title="Request Failed",
        )
        return
    if getattr(response, "sent", False):
        return
    await response.send(content="Done.")
