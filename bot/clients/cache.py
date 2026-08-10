from __future__ import annotations

import logging

from bot.db.repositories import ClientRepository
from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription

logger = logging.getLogger(__name__)


class ClientCache:
    """In-memory cache for clients and subscriptions."""

    def __init__(self, client_repo: ClientRepository) -> None:
        self._client_repo = client_repo
        self._by_id: dict[int, Client] = {}
        self._by_publish_channel: dict[int, ClientSubscription] = {}
        self._by_subscription_id: dict[int, ClientSubscription] = {}
        self._subscriptions_by_network: dict[int, list[ClientSubscription]] = {}

    @property
    def client_count(self) -> int:
        return len(self._by_id)

    @property
    def enabled_client_count(self) -> int:
        return sum(1 for client in self._by_id.values() if client.enabled)

    @property
    def subscription_count(self) -> int:
        return len(self._by_subscription_id)

    async def load_cache(self) -> None:
        clients = await self._client_repo.list_all()
        subscriptions = await self._client_repo.list_all_subscriptions()
        self._by_id = {client.id: client for client in clients}
        self._by_publish_channel = {
            sub.publish_channel_id: sub for sub in subscriptions
        }
        self._by_subscription_id = {sub.id: sub for sub in subscriptions}
        self._subscriptions_by_network = {}
        for sub in subscriptions:
            if sub.network_id is not None:
                self._subscriptions_by_network.setdefault(sub.network_id, []).append(sub)
        logger.info(
            "Client cache loaded",
            extra={
                "client_count": len(clients),
                "subscription_count": len(subscriptions),
            },
        )

    def get_client(self, client_id: int) -> Client | None:
        return self._by_id.get(client_id)

    def get_by_publish_channel(self, channel_id: int) -> ClientSubscription | None:
        return self._by_publish_channel.get(channel_id)

    def get_subscription(self, subscription_id: int) -> ClientSubscription | None:
        return self._by_subscription_id.get(subscription_id)

    def list_subscriptions_for_network(self, network_id: int) -> list[ClientSubscription]:
        return list(self._subscriptions_by_network.get(network_id, []))

    def get_enabled_subscription_by_publish(
        self,
        channel_id: int,
    ) -> ClientSubscription | None:
        sub = self._by_publish_channel.get(channel_id)
        if sub is None or not sub.enabled:
            return None
        client = self._by_id.get(sub.client_id)
        if client is None or not client.enabled:
            return None
        return sub
