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
        if relay_service.is_potential_feed_message(message):
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
        else:
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

        if self.bot.user is not None:
            from bot.services.profile_sticky import maybe_bump_profile_sticky
            from bot.ui.profile_views import EditProfileView

            async def _update_starter(thread_id: int, message_id: int) -> None:
                await context.profile_repo.update_starter_message_id(thread_id, message_id)

            await maybe_bump_profile_sticky(
                message,
                get_profile_by_source_channel=context.profile_repo.get_by_source_channel,
                update_starter_message_id=_update_starter,
                bot_user=self.bot.user,
                edit_view_factory=lambda channel_id: EditProfileView(self.bot, channel_id),
            )


async def setup(bot: NetworkRelayBot) -> None:
    await bot.add_cog(RelayCog(bot))
