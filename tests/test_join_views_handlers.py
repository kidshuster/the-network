from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from interaction_helpers import make_interaction, make_member

from bot.messages import render_text
from bot.ui.join_views import JoinNetworkModal, ModeratorReviewView

_DEFAULT_CONTEXT = object()


class _TestTextInput(discord.ui.TextInput):
    """TextInput stub with a preset value for unit tests."""

    def __init__(self, value: str) -> None:
        super().__init__(required=True)
        self._test_value = value

    @property
    def value(self) -> str:
        return self._test_value


class _TestFileUpload(discord.ui.FileUpload):
    """FileUpload stub that exposes preset attachment values in unit tests."""

    def __init__(self, values: list[MagicMock]) -> None:
        super().__init__(required=True)
        self._test_values = values

    @property
    def values(self) -> list[MagicMock]:
        return self._test_values


def _join_bot(
    *,
    guild_id: int = 100,
    context: MagicMock | None | object = _DEFAULT_CONTEXT,
) -> MagicMock:
    bot = MagicMock()
    bot.settings.guild_id = guild_id
    if context is _DEFAULT_CONTEXT:
        bot.bot_context = MagicMock()
    else:
        bot.bot_context = context
    return bot


def _join_modal(
    bot: MagicMock,
    *,
    name: str = "Acme Community",
    attachments: list[MagicMock] | None = None,
) -> JoinNetworkModal:
    modal = JoinNetworkModal(bot)
    name_field = discord.ui.Label(
        text="Name",
        component=_TestTextInput(name),
    )
    upload_values = attachments if attachments is not None else [MagicMock()]
    image_field = discord.ui.Label(
        text="Profile image",
        component=_TestFileUpload(upload_values),
    )
    modal._fields = {"name": name_field, "profile_image": image_field}
    return modal


@pytest.mark.asyncio
async def test_join_modal_rejects_non_hub_guild() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    guild.id = 999
    bot = _join_bot(guild_id=100)
    interaction = make_interaction(guild=guild, user=make_member(guild=guild))

    await _join_modal(bot).on_submit(interaction)

    interaction.followup.send.assert_awaited_once()
    assert interaction.followup.send.await_args.args[0] == render_text("hub_guild_only")


@pytest.mark.asyncio
async def test_join_modal_rejects_when_bot_not_ready() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = _join_bot(context=None)
    interaction = make_interaction(guild=guild, user=make_member(guild=guild))

    await _join_modal(bot).on_submit(interaction)

    interaction.followup.send.assert_awaited_once()
    assert interaction.followup.send.await_args.args[0] == render_text("bot_not_ready")


@pytest.mark.asyncio
async def test_join_modal_rejects_missing_profile_image() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = _join_bot()
    modal = _join_modal(bot, attachments=[])
    interaction = make_interaction(guild=guild, user=make_member(guild=guild))

    await modal.on_submit(interaction)

    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Request Failed"
    assert "profile image" in (embed.description or "").casefold()


@pytest.mark.asyncio
async def test_join_modal_renders_failure_embed_on_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = _join_bot()
    interaction = make_interaction(guild=guild, user=make_member(guild=guild))

    submit_result = MagicMock(success=False, error="Server name already exists.")
    monkeypatch.setattr(
        "bot.services.server_request_service.ServerRequestService.submit_request",
        AsyncMock(return_value=submit_result),
    )

    await _join_modal(bot).on_submit(interaction)

    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Request Failed"
    assert "already exists" in (embed.description or "")


@pytest.mark.asyncio
async def test_moderator_review_rejects_without_manage_guild() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=False)
    bot = _join_bot()
    interaction = make_interaction(guild=guild, user=member)
    view = ModeratorReviewView(bot, request_id=42)

    await view._approve_callback(interaction)

    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.await_args.args[0] == render_text(
        "manage_guild_required",
    )
    interaction.response.defer.assert_not_called()


@pytest.mark.asyncio
async def test_moderator_review_reports_bot_not_ready_after_defer() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=True)
    bot = _join_bot(context=None)
    interaction = make_interaction(guild=guild, user=member)
    view = ModeratorReviewView(bot, request_id=42)

    await view._deny_callback(interaction)

    interaction.response.defer.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()
    assert interaction.followup.send.await_args.args[0] == render_text("bot_not_ready")


@pytest.mark.asyncio
async def test_moderator_review_renders_failure_embed_on_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=True)
    bot = _join_bot()
    interaction = make_interaction(guild=guild, user=member)
    view = ModeratorReviewView(bot, request_id=42)

    deny_result = MagicMock(success=False, error="Request was already reviewed.", message=None)
    monkeypatch.setattr(
        "bot.services.server_request_service.ServerRequestService.deny_request",
        AsyncMock(return_value=deny_result),
    )

    await view._deny_callback(interaction)

    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Review Failed"
    assert "already reviewed" in (embed.description or "")


@pytest.mark.asyncio
async def test_moderator_review_renders_success_embed_on_deny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=True)
    bot = _join_bot()
    interaction = make_interaction(guild=guild, user=member)
    view = ModeratorReviewView(bot, request_id=42)

    deny_result = MagicMock(
        success=True,
        error=None,
        message="The join request was denied.",
    )
    monkeypatch.setattr(
        "bot.services.server_request_service.ServerRequestService.deny_request",
        AsyncMock(return_value=deny_result),
    )

    await view._deny_callback(interaction)

    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Request Denied"
    assert "denied" in (embed.description or "").casefold()
