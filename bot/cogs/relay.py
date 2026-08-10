from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)


class RelayCog(commands.Cog):
    def __init__(self, bot: NetworkRelayBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        context = self.bot.bot_context
        guild = channel.guild if hasattr(channel, "guild") else None
        if context is None or guild is None or guild.id != self.bot.settings.guild_id:
            return
        if not isinstance(channel, discord.TextChannel):
            return
        from bot.services.subscription_setup_sticky import (
            sync_subscription_setup_by_publish_channel,
        )

        try:
            await sync_subscription_setup_by_publish_channel(
                self.bot,
                context,
                guild,
                channel.id,
            )
        except Exception:
            logger.exception(
                "Subscription setup sync failed after webhooks update",
                extra={"channel_id": channel.id},
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        context = self.bot.bot_context
        if context is None:
            return

        from bot.services.hub_announcements import handle_network_announcements_message

        if message.guild is not None and message.guild.id == self.bot.settings.guild_id:
            await handle_network_announcements_message(self.bot, message)

        relay_service = context.relay_service
        if relay_service.is_potential_feed_message(message):
            try:
                result = await relay_service.relay_message(message)
                if result is None:
                    reason = relay_service.feed_reject_reason(message)
                    if reason is not None:
                        logger.info(
                            "Publish message not relayed",
                            extra={
                                "source_message_id": message.id,
                                "channel_id": message.channel.id,
                                "reason": reason,
                            },
                        )
            except Exception:
                logger.exception(
                    "Unexpected relay failure",
                    extra={"source_message_id": message.id, "channel_id": message.channel.id},
                )


async def setup(bot: NetworkRelayBot) -> None:
    await bot.add_cog(RelayCog(bot))
