from __future__ import annotations

import logging
from typing import Any

import discord

from bot.core.templates import render_embed, render_text

logger = logging.getLogger(__name__)


class DeferredResponse:
    """Track whether a deferred interaction sent its followup."""

    def __init__(self, interaction: discord.Interaction, *, ephemeral: bool = True) -> None:
        self._interaction = interaction
        self.ephemeral = ephemeral
        self.sent = False

    async def send(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("ephemeral", self.ephemeral)
        await self._interaction.followup.send(*args, **kwargs)
        self.sent = True

    async def send_text(
        self,
        key: str,
        *,
        ephemeral: bool | None = None,
        **kwargs: Any,
    ) -> None:
        await self.send(
            render_text(key, **kwargs),
            ephemeral=self.ephemeral if ephemeral is None else ephemeral,
        )

    async def send_embed_message(
        self,
        key: str,
        *,
        ephemeral: bool | None = None,
        **kwargs: Any,
    ) -> None:
        await self.send(
            embed=render_embed(key, **kwargs),
            ephemeral=self.ephemeral if ephemeral is None else ephemeral,
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


# Backward-compatible alias used by existing tests/call sites.
DeferredEphemeralResponse = DeferredResponse


async def defer_response(
    interaction: discord.Interaction,
    *,
    ephemeral: bool = True,
) -> DeferredResponse:
    await interaction.response.defer(ephemeral=ephemeral)
    return DeferredResponse(interaction, ephemeral=ephemeral)


async def defer_ephemeral(interaction: discord.Interaction) -> DeferredResponse:
    return await defer_response(interaction, ephemeral=True)
