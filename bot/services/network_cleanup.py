from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from bot.domain.network import Network
from bot.services.discord_cleanup import delete_channel
from bot.services.profile_cache import ProfileCache
from bot.services.profile_cleanup import ProfileCleanupService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NetworkCleanupResult:
    deleted_servers: int
    deleted_channels: int
    deleted_categories: int
    deleted_roles: int


class NetworkCleanupService:
    """Remove registered servers and network Discord infrastructure together."""

    def __init__(
        self,
        profile_cleanup: ProfileCleanupService,
        profile_cache: ProfileCache,
    ) -> None:
        self._profile_cleanup = profile_cleanup
        self._profile_cache = profile_cache

    async def cleanup_network(
        self,
        guild: discord.Guild,
        network: Network,
    ) -> NetworkCleanupResult:
        server_results = await self._profile_cleanup.cleanup_by_network_id(
            guild,
            network.id,
        )
        deleted_roles = sum(1 for result in server_results if result.deleted_role)
        await self._profile_cache.load_cache()

        deleted_channels, deleted_categories = await self._delete_network_categories(
            guild,
            network,
        )

        logger.info(
            "Network infrastructure cleaned up",
            extra={
                "network_key": network.key,
                "deleted_servers": len(server_results),
                "deleted_channels": deleted_channels,
                "deleted_categories": deleted_categories,
                "deleted_roles": deleted_roles,
            },
        )
        return NetworkCleanupResult(
            deleted_servers=len(server_results),
            deleted_channels=deleted_channels,
            deleted_categories=deleted_categories,
            deleted_roles=deleted_roles,
        )

    async def _delete_network_categories(
        self,
        guild: discord.Guild,
        network: Network,
    ) -> tuple[int, int]:
        category_ids = [network.feed_category_id]
        if network.profile_forum_channel_id is not None:
            category_ids.append(network.profile_forum_channel_id)

        channel_ids: set[int] = set()
        for channel in guild.channels:
            parent_id = getattr(channel, "category_id", None)
            if parent_id in category_ids and channel.id not in category_ids:
                channel_ids.add(channel.id)

        if network.concat_channel_id is not None:
            channel_ids.add(network.concat_channel_id)
        if network.join_channel_id is not None:
            channel_ids.add(network.join_channel_id)

        deleted_channels = 0
        for channel_id in sorted(channel_ids):
            if await delete_channel(guild, channel_id, label="network channel"):
                deleted_channels += 1

        deleted_categories = 0
        for category_id in category_ids:
            if await delete_channel(guild, category_id, label="network category"):
                deleted_categories += 1

        return deleted_channels, deleted_categories
