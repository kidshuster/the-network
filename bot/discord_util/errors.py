from __future__ import annotations

import discord


class DiscordStepError(Exception):
    """A Discord HTTP call failed during a named provisioning step."""

    def __init__(self, step: str, exc: discord.HTTPException) -> None:
        self.step = step
        self.exc = exc
        super().__init__(step)


def format_discord_step_error(step: str, exc: discord.HTTPException) -> str:
    code = getattr(exc, "code", None)
    lines = [
        f"**Failed step:** {step}",
        f"**Discord error:** {exc}",
    ]
    if code is not None:
        lines.append(f"**Error code:** `{code}`")

    if exc.status == 403 and code == 50013:
        lines.append(
            "**Note:** This is the bot's permission failing on that API call, not the "
            "channel where you ran the command. Slash-command replies only need you to "
            "see the channel; creating categories/channels uses the bot's guild role "
            "permissions."
        )
        if (
            "overwrite" in step.casefold()
            or "category" in step.casefold()
            or "channel" in step.casefold()
        ):
            lines.append(
                "If the bot role already has Manage Channels and Manage Roles, the "
                "overwrite payload for that step may be invalid."
            )

    return "\n".join(lines)
