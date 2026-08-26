from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from bot.contracts.recipes import recipe
from bot.features.channels.stickies.subscription import bump_announcements_sticky

if TYPE_CHECKING:
    from bot.contracts.recipes import RecipeContext

logger = logging.getLogger(__name__)


async def handle_client_announcements_message(
    bot: Any,
    message: discord.Message,
) -> None:
    context = bot.bot_context
    if context is None or message.guild is None or message.author.bot:
        return

    service = context.relay_service
    if not service.is_potential_announcements_message(message):
        return

    result = await service.relay_announcements_message(message)
    if result is None and (reason := service.announcements_reject_reason(message)) is not None:
        logger.info(
            "Client announcements message not relayed",
            extra={
                "source_message_id": message.id,
                "channel_id": message.channel.id,
                "reason": reason,
            },
        )
        return

    if result is not None and not result.success:
        logger.warning(
            "Client announcements relay failed",
            extra={
                "source_message_id": message.id,
                "channel_id": message.channel.id,
                "error": result.error,
            },
        )

    subscription = context.routing_service.resolve_announcements_subscription(
        message.channel.id
    )
    if subscription is None:
        # Cache may lag; fall back to store.
        subscription = await context.store.clients.get_subscription_by_announcements_channel(
            message.channel.id
        )
    if subscription is not None and isinstance(message.channel, discord.TextChannel):
        bot_user_id = bot.user.id if bot.user is not None else 0
        if bot_user_id:
            await bump_announcements_sticky(
                channel=message.channel,
                subscription=subscription,
                context=context,
                bot_user_id=bot_user_id,
            )


@recipe("hub.handle_client_announcement")
async def handle_client_announcement_recipe(
    recipe_context: RecipeContext,
    *,
    message: discord.Message,
) -> None:
    await handle_client_announcements_message(recipe_context.bot, message)
