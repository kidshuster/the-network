from __future__ import annotations

import logging
from typing import Any

import discord

from bot.core.templates import render_embed, render_text

logger = logging.getLogger(__name__)

# Deferred reply deleted (10008) or interaction token expired (10062).
_DEAD_INTERACTION_CODES = frozenset({10008, 10062})


def _is_dead_interaction_error(error: BaseException) -> bool:
    if not isinstance(error, discord.HTTPException):
        return False
    code = getattr(error, "code", None)
    return code in _DEAD_INTERACTION_CODES or isinstance(error, discord.NotFound)


class DeferredResponse:
    """Track whether a deferred interaction sent its followup."""

    def __init__(self, interaction: discord.Interaction, *, ephemeral: bool = True) -> None:
        self._interaction = interaction
        self.ephemeral = ephemeral
        self.sent = False
        self.used_channel_fallback = False

    async def send(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("ephemeral", self.ephemeral)
        try:
            await self._interaction.followup.send(*args, **kwargs)
            self.sent = True
            return
        except discord.HTTPException as error:
            if not _is_dead_interaction_error(error):
                raise
            logger.warning(
                "Interaction followup unavailable (deferred reply missing or expired); "
                "trying fallbacks",
                exc_info=error,
            )

        edit_kwargs = {key: value for key, value in kwargs.items() if key != "ephemeral"}
        try:
            await self._interaction.edit_original_response(*args, **edit_kwargs)
            self.sent = True
            return
        except discord.HTTPException as error:
            if not _is_dead_interaction_error(error):
                raise
            logger.warning(
                "Could not edit original interaction response; trying channel fallback",
                exc_info=error,
            )

        if await self._send_channel_fallback(*args, **edit_kwargs):
            self.sent = True
            self.used_channel_fallback = True
            return

        logger.error(
            "Could not deliver deferred command response after dead interaction"
        )

    async def _send_channel_fallback(self, *args: Any, **kwargs: Any) -> bool:
        channel = self._interaction.channel
        if channel is None or not hasattr(channel, "send"):
            return False
        send_kwargs = dict(kwargs)
        send_kwargs.setdefault("silent", True)
        # Ephemeral-only kwargs are invalid on channel messages.
        send_kwargs.pop("ephemeral", None)
        content = send_kwargs.get("content")
        note = (
            "Could not update the ephemeral reply (it may have been dismissed). "
            "Result:"
        )
        if content:
            send_kwargs["content"] = f"{note}\n{content}"
        elif args:
            # First positional is often content for discord.py Messageable.send.
            first, *rest = args
            if isinstance(first, str):
                args = (f"{note}\n{first}", *rest)
            else:
                send_kwargs["content"] = note
                args = (first, *rest)
        else:
            send_kwargs["content"] = note
        try:
            await channel.send(*args, **send_kwargs)
        except discord.HTTPException:
            logger.exception("Channel fallback for deferred response failed")
            return False
        logger.info(
            "Posted command result to channel after dead interaction followup"
        )
        return True

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
