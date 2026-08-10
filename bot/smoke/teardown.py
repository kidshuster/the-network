from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from bot.smoke.provision_flow import (
    cleanup_join_requests_smoke_artifacts,
    cleanup_smoke_client,
)
from bot.smoke.resource_guard import (
    cleanup_guild_test_artifacts,
    cleanup_hub_rebuild_smoke_artifacts,
    cleanup_orphan_smoke_subscription_channels,
    is_smoke_client_server_name,
)

if TYPE_CHECKING:
    from bot.context import BotContext

logger = logging.getLogger(__name__)


@dataclass
class TeardownResult:
    removed_clients: list[str] = field(default_factory=list)
    removed_artifacts: list[str] = field(default_factory=list)
    manual_channels: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


async def teardown_smoke_guild(
    guild: discord.Guild,
    context: BotContext,
    bot_member: discord.Member,
) -> TeardownResult:
    """Remove all smoke clients and leftover Discord artifacts from the configured guild."""
    result = TeardownResult()

    for client in await context.client_repo.list_all():
        if client.guild_id != guild.id:
            continue
        if not is_smoke_client_server_name(client.server_name):
            continue
        try:
            await cleanup_smoke_client(
                guild,
                context,
                server_name=client.server_name,
                bot_member=bot_member,
            )
            result.removed_clients.append(client.server_name)
        except Exception as exc:
            message = f"client {client.server_name}: {exc}"
            result.errors.append(message)
            logger.warning("Smoke teardown: %s", message)

    try:
        await cleanup_join_requests_smoke_artifacts(guild, context, bot_member)
    except Exception as exc:
        result.errors.append(f"join-requests cleanup: {exc}")

    result.removed_artifacts.extend(await cleanup_guild_test_artifacts(guild))
    result.removed_artifacts.extend(
        await cleanup_hub_rebuild_smoke_artifacts(guild, bot_member)
    )
    result.removed_artifacts.extend(await cleanup_guild_test_artifacts(guild))

    try:
        result.manual_channels.extend(
            await cleanup_orphan_smoke_subscription_channels(guild, context)
        )
    except Exception as exc:
        result.errors.append(f"orphan channel cleanup: {exc}")

    await context.client_cache.load_cache()
    await context.routing_service.load_cache()
    return result
