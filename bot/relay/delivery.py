from __future__ import annotations

from typing import Any

import discord


def apply_silent_delivery(
    kwargs: dict[str, Any],
    *,
    notify: bool = False,
) -> dict[str, Any]:
    """Suppress mobile/desktop push notifications for a channel message."""
    if not notify:
        kwargs["silent"] = True
    return kwargs


def build_moderator_join_request_send_kwargs(
    human_moderator_role: discord.Role | None,
) -> dict[str, Any]:
    """Notify moderators about a new join request without pinging @everyone."""
    kwargs: dict[str, Any] = {"silent": False}
    if human_moderator_role is not None:
        kwargs["content"] = human_moderator_role.mention
        kwargs["allowed_mentions"] = discord.AllowedMentions(
            roles=[human_moderator_role],
        )
    else:
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
    return kwargs
