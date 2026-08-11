from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord

from bot.app.discord.errors import report_error, respond_to_error
from bot.app.discord.responses import DeferredEphemeralResponse
from bot.app.recipes import RecipeRegistryError
from bot.errors import UserFacingError


def _guild_with_moderator_channel() -> tuple[MagicMock, MagicMock]:
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "admin"
    channel.send = AsyncMock()
    guild.public_updates_channel = channel
    guild.text_channels = [channel]
    return guild, channel


async def test_user_error_is_dynamic_and_reported_to_community_moderator_channel() -> None:
    guild, moderator_channel = _guild_with_moderator_channel()
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.followup.send = AsyncMock()
    response = DeferredEphemeralResponse(interaction)
    bot = MagicMock()
    error = UserFacingError(
        "Network `alpha` was not found.",
        title="Network Not Found",
    )

    await respond_to_error(
        bot,
        interaction,
        response,
        error,
        operation="network.delete",
    )

    user_embed = interaction.followup.send.await_args.kwargs["embed"]
    moderator_embed = moderator_channel.send.await_args.kwargs["embed"]
    assert user_embed.title == "Network Not Found"
    assert user_embed.description == "Network `alpha` was not found."
    assert user_embed.footer.text == moderator_embed.footer.text
    assert "network.delete" in moderator_embed.description


async def test_unexpected_recipe_error_hides_internal_detail_from_user() -> None:
    guild, moderator_channel = _guild_with_moderator_channel()
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.followup.send = AsyncMock()
    response = DeferredEphemeralResponse(interaction)
    internal = RuntimeError("database password leaked here")
    error = RecipeRegistryError("Recipe failed", recipe="network.create")
    error.__cause__ = internal

    await respond_to_error(
        MagicMock(),
        interaction,
        response,
        error,
        operation="network.create",
    )

    user_embed = interaction.followup.send.await_args.kwargs["embed"]
    moderator_embed = moderator_channel.send.await_args.kwargs["embed"]
    assert "database password" not in user_embed.description
    assert "database password" not in moderator_embed.description
    assert "RuntimeError" in moderator_embed.description


async def test_error_report_does_not_guess_when_community_channel_is_missing() -> None:
    guild, moderator_channel = _guild_with_moderator_channel()
    guild.public_updates_channel = None

    reference = await report_error(
        MagicMock(),
        guild,
        UserFacingError("Safe detail"),
        operation="test.operation",
    )

    assert reference
    moderator_channel.send.assert_not_awaited()
