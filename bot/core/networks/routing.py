from __future__ import annotations

import logging

from bot.core.clients.cache import ClientCache
from bot.core.database.store import ClientStore, NetworkStore
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.errors import RoutingError
from bot.core.models.network import Network

logger = logging.getLogger(__name__)


class RoutingService:
    """In-memory cache for networks and client subscription routes."""

    def __init__(
        self,
        network_repo: NetworkStore,
        client_repo: ClientStore | None = None,
    ) -> None:
        self._network_repo = network_repo
        self._client_repo = client_repo
        self._by_key: dict[str, Network] = {}
        self._by_id: dict[int, Network] = {}
        self._concat_channels: set[int] = set()
        self._client_cache: ClientCache | None = None

    def attach_client_cache(self, client_cache: ClientCache) -> None:
        self._client_cache = client_cache

    @property
    def network_count(self) -> int:
        return len(self._by_key)

    @property
    def enabled_network_count(self) -> int:
        return sum(1 for network in self._by_key.values() if network.enabled)

    async def load_cache(self) -> None:
        networks = await self._network_repo.list_all()
        self._by_key = {n.key: n for n in networks}
        self._by_id = {n.id: n for n in networks}
        self._concat_channels = {
            n.concat_channel_id for n in networks if n.concat_channel_id is not None
        }
        logger.info(
            "Network route cache loaded",
            extra={"network_count": len(networks)},
        )

    def is_concat_channel(self, channel_id: int) -> bool:
        return channel_id in self._concat_channels

    def get_by_key(self, key: str) -> Network | None:
        return self._by_key.get(key)

    def get_by_id(self, network_id: int) -> Network | None:
        return self._by_id.get(network_id)

    def require_by_key(self, key: str) -> Network:
        network = self.get_by_key(key)
        if network is None:
            raise RoutingError(f"Network '{key}' was not found.")
        return network

    def resolve_publish_subscription(self, publish_channel_id: int) -> ClientSubscription | None:
        if self._client_cache is None:
            return None
        return self._client_cache.get_enabled_subscription_by_publish(publish_channel_id)

    def list_network_subscriptions(self, network_id: int) -> list[ClientSubscription]:
        if self._client_cache is None:
            return []
        return self._client_cache.list_subscriptions_for_network(network_id)
