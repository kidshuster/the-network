from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.core.relay.delivery import (
    apply_silent_delivery,
    build_moderator_join_request_send_kwargs,
)


def test_apply_silent_delivery_defaults_to_silent() -> None:
    kwargs = apply_silent_delivery({})
    assert kwargs == {"silent": True}


def test_apply_silent_delivery_notify_skips_silent() -> None:
    kwargs = apply_silent_delivery({}, notify=True)
    assert "silent" not in kwargs


def test_build_moderator_join_request_send_kwargs_without_role() -> None:
    kwargs = build_moderator_join_request_send_kwargs(None)
    assert kwargs["silent"] is False
    assert kwargs.get("content") is None
    assert isinstance(kwargs["allowed_mentions"], discord.AllowedMentions)


def test_build_moderator_join_request_send_kwargs_pings_moderator_role() -> None:
    role = MagicMock(spec=discord.Role)
    role.mention = "<@&123>"
    kwargs = build_moderator_join_request_send_kwargs(role)
    assert kwargs["silent"] is False
    assert kwargs["content"] == "<@&123>"
    allowed = kwargs["allowed_mentions"]
    assert isinstance(allowed, discord.AllowedMentions)
    assert allowed.roles == [role]
