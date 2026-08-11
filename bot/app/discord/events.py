from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bot.app.discord.errors import report_error

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot


def register_recipe_events(bot: NetworkRelayBot) -> None:
    async def on_message(message: discord.Message) -> None:
        if bot.bot_context is None:
            return
        try:
            await bot.recipe_registry.dispatch("discord.message", message=message)
        except Exception as error:
            await report_error(bot, message.guild, error, operation="discord.message")

    async def on_webhooks_update(channel: discord.abc.GuildChannel) -> None:
        guild = getattr(channel, "guild", None)
        if bot.bot_context is None or guild is None or guild.id != bot.settings.guild_id:
            return
        try:
            await bot.recipe_registry.dispatch("discord.webhooks_update", channel=channel)
        except Exception as error:
            await report_error(bot, guild, error, operation="discord.webhooks_update")

    bot.add_listener(on_message, "on_message")
    bot.add_listener(on_webhooks_update, "on_webhooks_update")
