"""Server lifecycle recipes (init / probe / uninit / sync-join-guide)."""

from __future__ import annotations

from typing import Any

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.errors import UserFacingError


@recipe("server.init")
async def initialize_server(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> Any:
    guild = interaction.guild
    if guild is None or guild.id != recipe_context.bot.settings.guild_id:
        raise UserFacingError("This command can only be used in the configured hub guild.")
    bot_member = guild.me
    if bot_member is None:
        raise UserFacingError("Bot member is unavailable.")
    return await recipe_context.run(
        "hub.initialize",
        guild=guild,
        bot_member=bot_member,
        interaction=interaction,
    )


@recipe("server.probe")
async def probe_server(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> Any:
    from bot.features.recipes.hub.probe import run_server_probe

    guild = interaction.guild
    if guild is None or guild.id != recipe_context.bot.settings.guild_id:
        raise UserFacingError("This command can only be used in the configured hub guild.")
    bot_member = guild.me
    if bot_member is None:
        raise UserFacingError("Bot member is unavailable.")
    return await run_server_probe(
        guild,
        bot_member,
        settings=recipe_context.bot.settings,
        context=recipe_context.core,
    )


@recipe("server.uninit")
async def uninitialize_server(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> Any:
    guild = interaction.guild
    if guild is None or guild.id != recipe_context.bot.settings.guild_id:
        raise UserFacingError("This command can only be used in the configured hub guild.")
    bot_member = guild.me
    if bot_member is None:
        raise UserFacingError("Bot member is unavailable.")
    await recipe_context.run("hub.teardown_installs", guild_id=guild.id)
    result = await recipe_context.run(
        "hub.uninitialize",
        guild=guild,
        bot_member=bot_member,
    )
    data_result = await recipe_context.run("hub.reset_data", guild_id=guild.id)
    if (note := data_result.summary_note()) is not None:
        result.notes.append(note)
    return result


@recipe("server.sync_join_guide")
async def sync_join_guide(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> tuple[Any, discord.TextChannel]:
    from bot.features.channels.resolve import resolve_join_the_network_channel
    from bot.features.channels.stickies.join import sync_hub_join_sticky

    guild = interaction.guild
    if guild is None or guild.me is None:
        raise UserFacingError("Guild or bot member is unavailable.")
    channel = resolve_join_the_network_channel(guild)
    if channel is None:
        raise UserFacingError("The join-the-network channel was not found.")
    view = recipe_context.bot.make_view_registry().register_join_network_view()
    result = await sync_hub_join_sticky(
        guild,
        guild.me,
        channel,
        view,
        get_setting=recipe_context.core.store.settings.get,
        set_setting=recipe_context.core.store.settings.set,
        wipe_channel=True,
    )
    return result, channel
