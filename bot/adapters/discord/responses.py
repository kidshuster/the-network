from __future__ import annotations

import logging
from typing import Any

import discord

from bot.presentation import render_embed, render_text

logger = logging.getLogger(__name__)


class DeferredEphemeralResponse:
    """Track whether a deferred slash command sent its followup."""

    def __init__(self, interaction: discord.Interaction) -> None:
        self._interaction = interaction
        self.sent = False

    async def send(self, *args: Any, **kwargs: Any) -> None:
        await self._interaction.followup.send(*args, **kwargs)
        self.sent = True

    async def send_text(
        self,
        key: str,
        *,
        ephemeral: bool | None = True,
        **kwargs: Any,
    ) -> None:
        await self.send(render_text(key, **kwargs), ephemeral=ephemeral)

    async def send_embed_message(
        self,
        key: str,
        *,
        ephemeral: bool | None = True,
        **kwargs: Any,
    ) -> None:
        await self.send(
            embed=render_embed(key, **kwargs),
            ephemeral=ephemeral,
        )

    async def send_error(
        self,
        description: str,
        *,
        title: str = "Operation Failed",
        reference: str = "none",
    ) -> None:
        await self.send(
            embed=render_embed(
                "error",
                title=title,
                description=description,
                reference=reference,
            ),
            ephemeral=True,
        )

    async def ensure_sent(self) -> None:
        if self.sent:
            return
        logger.error("Deferred slash command finished without sending a followup")
        try:
            await self.send(
                embed=render_embed(
                    "error",
                    title="Unexpected Error",
                    description="The operation completed without returning a response.",
                    reference="none",
                ),
                ephemeral=True,
            )
        except discord.HTTPException:
            logger.exception("Could not send fallback followup for deferred command")


async def defer_ephemeral(interaction: discord.Interaction) -> DeferredEphemeralResponse:
    await interaction.response.defer(ephemeral=True)
    return DeferredEphemeralResponse(interaction)
