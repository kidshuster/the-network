from __future__ import annotations

import logging

import discord

from bot.messages import render_embed

logger = logging.getLogger(__name__)


class DeferredEphemeralResponse:
    """Track whether a deferred slash command sent its followup."""

    def __init__(self, interaction: discord.Interaction) -> None:
        self._interaction = interaction
        self.sent = False

    async def send(self, *args, **kwargs) -> None:
        await self._interaction.followup.send(*args, **kwargs)
        self.sent = True

    async def send_failure(self, title: str, description: str) -> None:
        await self.send(
            embed=render_embed("command_failure", title=title, description=description),
            ephemeral=True,
        )

    async def ensure_sent(self) -> None:
        if self.sent:
            return
        logger.error("Deferred slash command finished without sending a followup")
        try:
            await self.send(
                embed=render_embed("command_error"),
                ephemeral=True,
            )
        except discord.HTTPException:
            logger.exception("Could not send fallback followup for deferred command")


async def defer_ephemeral(interaction: discord.Interaction) -> DeferredEphemeralResponse:
    await interaction.response.defer(ephemeral=True)
    return DeferredEphemeralResponse(interaction)
