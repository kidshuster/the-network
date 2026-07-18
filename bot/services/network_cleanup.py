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
    deleted_category: bool
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

        deleted_channels, deleted_category = await self._delete_feed_category_tree(
            guild,
            network,
        )

        logger.info(
            "Network infrastructure cleaned up",
            extra={
                "network_key": network.key,
                "deleted_servers": len(server_results),
                "deleted_channels": deleted_channels,
                "deleted_category": deleted_category,
                "deleted_roles": deleted_roles,
            },
        )
        return NetworkCleanupResult(
            deleted_servers=len(server_results),
            deleted_channels=deleted_channels,
            deleted_category=deleted_category,
            deleted_roles=deleted_roles,
        )

    async def _delete_feed_category_tree(
        self,
        guild: discord.Guild,
        network: Network,
    ) -> tuple[int, bool]:
        category_id = network.feed_category_id
        channel_ids: set[int] = set()

        for channel in guild.channels:
            if getattr(channel, "category_id", None) == category_id:
                channel_ids.add(channel.id)

        for known_id in (network.concat_channel_id, network.profile_forum_channel_id):
            if known_id is not None:
                channel_ids.add(known_id)

        channel_ids.discard(category_id)

        deleted_channels = 0
        for channel_id in sorted(channel_ids):
            if await delete_channel(guild, channel_id, label="network channel"):
                deleted_channels += 1

        deleted_category = await delete_channel(
            guild,
            category_id,
            label="network feed category",
        )
        return deleted_channels, deleted_category
