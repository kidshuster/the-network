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
    async def on_message(self, message: discord.Message) -> None:
        context = self.bot.bot_context
        if context is None:
            return

        relay_service = context.relay_service
        if not relay_service.is_potential_feed_message(message):
            reason = relay_service.feed_reject_reason(message)
            if reason is not None:
                logger.info(
                    "Feed message not relayed",
                    extra={
                        "source_message_id": message.id,
                        "channel_id": message.channel.id,
                        "webhook_id": message.webhook_id,
                        "reason": reason,
                    },
                )
            return

        try:
            result = await relay_service.relay_message(message)
            if result is None:
                reason = relay_service.feed_reject_reason(message)
                if reason is not None:
                    logger.info(
                        "Feed message not relayed",
                        extra={
                            "source_message_id": message.id,
                            "channel_id": message.channel.id,
                            "webhook_id": message.webhook_id,
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
