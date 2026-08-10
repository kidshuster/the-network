from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.cogs._responses import DeferredEphemeralResponse, defer_ephemeral
from bot.messages import render_embed


@pytest.mark.asyncio
async def test_send_marks_sent() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    response = DeferredEphemeralResponse(interaction)
    assert response.sent is False
    await response.send(content="done", ephemeral=True)
    assert response.sent is True
    interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_failure_renders_command_failure_embed() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    response = DeferredEphemeralResponse(interaction)
    await response.send_failure("Init failed", "Missing permissions")

    args, kwargs = interaction.followup.send.await_args
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "Init failed"
    assert kwargs["embed"].description == "Missing permissions"
    assert response.sent is True


@pytest.mark.asyncio
async def test_ensure_sent_sends_command_error_when_nothing_sent() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    response = DeferredEphemeralResponse(interaction)
    await response.ensure_sent()

    kwargs = interaction.followup.send.await_args.kwargs
    expected = render_embed("command_error")
    assert kwargs["embed"].title == expected.title
    assert response.sent is True


@pytest.mark.asyncio
async def test_ensure_sent_noop_when_already_sent() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    response = DeferredEphemeralResponse(interaction)
    response.sent = True
    await response.ensure_sent()
    interaction.followup.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_propagates_followup_http_exception() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "Interaction expired"),
    )

    response = DeferredEphemeralResponse(interaction)
    with pytest.raises(discord.HTTPException):
        await response.send("done", ephemeral=True)
    assert response.sent is False


@pytest.mark.asyncio
async def test_ensure_sent_swallows_followup_http_exception() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "Interaction expired"),
    )

    response = DeferredEphemeralResponse(interaction)
    await response.ensure_sent()

    interaction.followup.send.assert_awaited_once()
    assert response.sent is False
