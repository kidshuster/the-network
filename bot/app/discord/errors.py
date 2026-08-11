from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Protocol

import discord

from bot.app.recipes import RecipeRegistryError
from bot.app.templates import render_embed
from bot.errors import UserFacingError

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot

logger = logging.getLogger(__name__)


class ErrorResponse(Protocol):
    async def send_error(
        self,
        description: str,
        *,
        title: str = "Operation Failed",
        reference: str = "none",
    ) -> None: ...


def _reference(error: BaseException) -> str:
    if isinstance(error, RecipeRegistryError):
        return error.reference
    return secrets.token_hex(4)


def _public_error(error: BaseException) -> UserFacingError | None:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, UserFacingError):
            return current
        current = current.__cause__
    return None


def _moderator_channel(guild: discord.Guild | None) -> discord.TextChannel | None:
    if guild is None:
        return None
    channel = guild.public_updates_channel
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


async def report_error(
    bot: NetworkRelayBot,
    guild: discord.Guild | None,
    error: BaseException,
    *,
    operation: str,
) -> str:
    reference = _reference(error)
    public = _public_error(error)
    logger.error(
        "Discord operation failed",
        exc_info=(type(error), error, error.__traceback__),
        extra={"operation": operation, "error_reference": reference},
    )
    channel = _moderator_channel(guild)
    if channel is None:
        logger.warning(
            "Could not report error to moderator channel",
            extra={"operation": operation, "error_reference": reference},
        )
        return reference
    detail = public.message if public is not None else "Unexpected internal failure. See bot logs."
    try:
        await channel.send(
            embed=render_embed(
                "error",
                title="Bot Error",
                description=(
                    f"**Operation:** `{operation}`\n"
                    f"**Type:** `{type(error.__cause__ or error).__name__}`\n"
                    f"**Detail:** {detail}"
                ),
                reference=reference,
            ),
            silent=True,
        )
    except discord.HTTPException:
        logger.exception(
            "Failed to send error report to moderator channel",
            extra={"operation": operation, "error_reference": reference},
        )
    return reference


async def respond_to_error(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    response: ErrorResponse,
    error: BaseException,
    *,
    operation: str,
) -> None:
    reference = await report_error(bot, interaction.guild, error, operation=operation)
    public = _public_error(error)
    title = public.title if public is not None else "Unexpected Error"
    description = (
        public.message
        if public is not None
        else "The operation failed unexpectedly. Moderators have been notified."
    )
    await response.send_error(
        description,
        title=title,
        reference=reference,
    )


async def respond_with_error(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    response: ErrorResponse,
    message: str,
    *,
    operation: str,
    title: str = "Operation Failed",
) -> None:
    await respond_to_error(
        bot,
        interaction,
        response,
        UserFacingError(message, title=title),
        operation=operation,
    )
