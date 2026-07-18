from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.services.discord_errors import format_discord_step_error


def _http_exception(*, status: int, code: int | None, message: str) -> discord.HTTPException:
    exc = discord.HTTPException(MagicMock(), message)
    exc.status = status
    exc.code = code
    return exc


def test_format_discord_step_error_includes_step_and_code() -> None:
    exc = _http_exception(status=403, code=50013, message="Forbidden")
    text = format_discord_step_error("create feed category", exc)
    assert "create feed category" in text
    assert "50013" in text
    assert "not the channel where you ran the command" in text


def test_format_discord_step_error_without_code() -> None:
    exc = _http_exception(status=500, code=None, message="Server error")
    text = format_discord_step_error("create #feed channel", exc)
    assert "create #feed channel" in text
    assert "Error code" not in text
