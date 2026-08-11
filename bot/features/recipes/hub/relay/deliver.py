from __future__ import annotations

import logging
from typing import Any

import discord

from bot.app.recipes.registry import recipe
from bot.app.recipes.runtime import RecipeContext

logger = logging.getLogger(__name__)


@recipe("relay.deliver")
async def deliver_relay_message(
    recipe_context: RecipeContext,
    *,
    message: discord.Message,
) -> Any:
    service = recipe_context.core.relay_service
    if not service.is_potential_feed_message(message):
        return None
    result = await service.relay_message(message)
    if result is None and (reason := service.feed_reject_reason(message)) is not None:
        logger.info(
            "Publish message not relayed",
            extra={
                "source_message_id": message.id,
                "channel_id": message.channel.id,
                "reason": reason,
            },
        )
    return result
