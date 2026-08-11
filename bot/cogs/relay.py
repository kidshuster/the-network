from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

class RelayCog(commands.Cog):
    def __init__(self, bot: NetworkRelayBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        context = self.bot.bot_context
        guild = channel.guild if hasattr(channel, "guild") else None
        if context is None or guild is None or guild.id != self.bot.settings.guild_id:
            return
        await self.bot.recipe_registry.dispatch("discord.webhooks_update", channel=channel)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        context = self.bot.bot_context
        if context is None:
            return

        await self.bot.recipe_registry.dispatch("discord.message", message=message)


async def setup(bot: NetworkRelayBot) -> None:
    await bot.add_cog(RelayCog(bot))
