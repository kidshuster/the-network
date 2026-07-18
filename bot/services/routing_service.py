from __future__ import annotations

import logging

from bot.db.repositories import NetworkRepository
from bot.domain.errors import RoutingError
from bot.domain.network import Network
from bot.domain.network_route import CategoryRoute

logger = logging.getLogger(__name__)


class RoutingService:
    """In-memory cache mapping feed categories to network output routes."""

    def __init__(self, network_repo: NetworkRepository) -> None:
        self._network_repo = network_repo
        self._by_category: dict[int, Network] = {}
        self._by_key: dict[str, Network] = {}
        self._by_id: dict[int, Network] = {}
        self._by_output_channel: dict[int, Network] = {}
        self._concat_channels: set[int] = set()

    @property
    def network_count(self) -> int:
        return len(self._by_key)

    @property
    def enabled_network_count(self) -> int:
        return sum(1 for network in self._by_key.values() if network.enabled)

    async def load_cache(self) -> None:
        networks = await self._network_repo.list_all()
        self._by_category = {n.feed_category_id: n for n in networks}
        self._by_key = {n.key: n for n in networks}
        self._by_id = {n.id: n for n in networks}
        self._by_output_channel = {n.output_channel_id: n for n in networks}
        self._concat_channels = {
            n.concat_channel_id for n in networks if n.concat_channel_id is not None
        }
        logger.info(
            "Network route cache loaded",
            extra={"network_count": len(networks)},
        )

    def get_by_key(self, key: str) -> Network | None:
        return self._by_key.get(key)

    def get_by_id(self, network_id: int) -> Network | None:
        return self._by_id.get(network_id)

    def is_concat_channel(self, channel_id: int) -> bool:
        return channel_id in self._concat_channels

    def get_by_category(self, category_id: int) -> Network | None:
        return self._by_category.get(category_id)

    def resolve_category_route(self, category_id: int) -> CategoryRoute | None:
        network = self._by_category.get(category_id)
        if network is None or not network.enabled:
            return None
        return CategoryRoute(
            feed_category_id=category_id,
            network=network,
            output_channel_id=network.output_channel_id,
            concat_channel_id=network.concat_channel_id,
        )

    def resolve_source_channel(
        self,
        channel_id: int,
        parent_id: int | None,
    ) -> CategoryRoute | None:
        """Resolve a source feed channel via its parent category (Phase 2)."""
        if parent_id is None:
            return None
        return self.resolve_category_route(parent_id)

    def require_by_key(self, key: str) -> Network:
        network = self.get_by_key(key)
        if network is None:
            raise RoutingError(f"Network '{key}' was not found.")
        return network
