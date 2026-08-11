from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from interaction_helpers import make_interaction, make_member
from widget_helpers import wire_widget_bot

from bot.app.widgets import render_modal, render_view
from bot.app.widgets.dispatch import RenderedModal
from bot.core.templates import render_text


class _TestTextInput(discord.ui.TextInput):
    def __init__(self, value: str) -> None:
        super().__init__(required=True)
        self._test_value = value

    @property
    def value(self) -> str:
        return self._test_value


class _TestFileUpload(discord.ui.FileUpload):
    def __init__(self, values: list[MagicMock]) -> None:
        super().__init__(required=True)
        self._test_values = values

    @property
    def values(self) -> list[MagicMock]:
        return self._test_values


def _join_bot(*, guild_id: int = 100, context: object | None = ...) -> MagicMock:  # type: ignore[assignment]
    bot = wire_widget_bot()
    bot.settings.guild_id = guild_id
    if context is ...:
        bot.bot_context = MagicMock()
    else:
        bot.bot_context = context  # type: ignore[assignment]
    return bot


def _join_modal(
    bot: MagicMock,
    *,
    name: str = "Acme Community",
    attachments: list[MagicMock] | None = None,
) -> RenderedModal:
    modal = render_modal("join_network", bot)
    name_field = discord.ui.Label(
        text="Name",
        component=_TestTextInput(name),
    )
    upload_values = attachments if attachments is not None else [MagicMock()]
    image_field = discord.ui.Label(
        text="Profile image",
        component=_TestFileUpload(upload_values),
    )
    modal._labels = {"server_name": name_field, "profile_image": image_field}
    modal.field_ids = ["server_name", "profile_image"]
    modal.file_fields = {"profile_image"}
    return modal


async def _click(view: object, label: str, interaction: discord.Interaction) -> None:
    for child in getattr(view, "children", []):
        if isinstance(child, discord.ui.Button) and child.label == label:
            await child.callback(interaction)
            return
    raise AssertionError(f"Button {label!r} not found")


def _auth_message(interaction: MagicMock) -> str:
    return str(interaction.response.send_message.await_args.args[0])


@pytest.mark.asyncio
async def test_join_modal_rejects_non_hub_guild() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    guild.id = 999
    bot = _join_bot(guild_id=100)
    interaction = make_interaction(guild=guild, user=make_member(guild=guild))

    await _join_modal(bot).on_submit(interaction)

    assert _auth_message(interaction) == render_text("hub_guild_only")


@pytest.mark.asyncio
async def test_join_modal_rejects_when_bot_not_ready() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = _join_bot(context=None)
    interaction = make_interaction(guild=guild, user=make_member(guild=guild))

    await _join_modal(bot).on_submit(interaction)

    assert _auth_message(interaction) == render_text("bot_not_ready")


@pytest.mark.asyncio
async def test_join_modal_rejects_missing_profile_image() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = _join_bot()
    modal = _join_modal(bot, attachments=[])
    interaction = make_interaction(guild=guild, user=make_member(guild=guild))

    await modal.on_submit(interaction)

    assert "profile image" in _auth_message(interaction).casefold()


@pytest.mark.asyncio
async def test_join_modal_renders_failure_embed_on_service_error() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = _join_bot()
    interaction = make_interaction(guild=guild, user=make_member(guild=guild))
    bot.dispatch_trigger = AsyncMock(
        return_value=MagicMock(success=False, error="Server name already exists."),
    )

    await _join_modal(bot).on_submit(interaction)

    bot.dispatch_trigger.assert_awaited_once()
    assert bot.dispatch_trigger.await_args.args[0] == "request.submit"
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Request Failed"
    assert "already exists" in (embed.description or "")


@pytest.mark.asyncio
async def test_moderator_review_rejects_without_manage_guild() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=False)
    bot = _join_bot()
    interaction = make_interaction(guild=guild, user=member)
    view = render_view("moderator_review", bot, request_id=42)

    await _click(view, "Accept", interaction)

    assert _auth_message(interaction) == render_text("manage_guild_required")
    bot.dispatch_trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_moderator_review_reports_bot_not_ready() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=True)
    bot = _join_bot(context=None)
    interaction = make_interaction(guild=guild, user=member)
    view = render_view("moderator_review", bot, request_id=42)

    await _click(view, "Deny", interaction)

    assert _auth_message(interaction) == render_text("bot_not_ready")


@pytest.mark.asyncio
async def test_moderator_review_renders_failure_embed_on_service_error() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=True)
    bot = _join_bot()
    interaction = make_interaction(guild=guild, user=member)
    view = render_view("moderator_review", bot, request_id=42)
    bot.dispatch_trigger = AsyncMock(
        return_value=MagicMock(
            success=False,
            error="Request was already reviewed.",
            message=None,
        ),
    )

    await _click(view, "Deny", interaction)

    bot.dispatch_trigger.assert_awaited_once()
    assert bot.dispatch_trigger.await_args.args[0] == "request.deny"
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Request Failed"
    assert "already reviewed" in (embed.description or "")


@pytest.mark.asyncio
async def test_moderator_review_renders_success_embed_on_deny() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=True)
    bot = _join_bot()
    interaction = make_interaction(guild=guild, user=member)
    view = render_view("moderator_review", bot, request_id=42)
    bot.dispatch_trigger = AsyncMock(
        return_value=MagicMock(
            success=True,
            error=None,
            message="The join request was denied.",
        ),
    )

    async def _present(name: str, **kwargs: object) -> None:
        from bot.core.templates import render_embed

        del name
        await kwargs["response"].send(  # type: ignore[index]
            embed=render_embed(
                "review_success",
                label="Denied",
                colour="red",
                description=str(getattr(kwargs["value"], "message", "")),
            )
        )

    bot.recipe_registry.run = AsyncMock(side_effect=_present)

    await _click(view, "Deny", interaction)

    bot.dispatch_trigger.assert_awaited_once()
    assert bot.dispatch_trigger.await_args.args[0] == "request.deny"
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Request Denied"
    assert "denied" in (embed.description or "").casefold()
