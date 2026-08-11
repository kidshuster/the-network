from __future__ import annotations

from dataclasses import dataclass

from bot.db.connection import Database
from bot.db.domains.records import ClientStore as ClientStore
from bot.db.domains.records import NetworkStore as NetworkStore
from bot.db.domains.records import RelayStore as RelayStore
from bot.db.domains.records import RequestStore as RequestStore
from bot.db.domains.records import SettingsStore as SettingsStore
from bot.db.domains.resources import ManagedResource, ResourceStore
from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription


@dataclass(frozen=True)
class LayoutState:
    guild_id: int
    clients: tuple[Client, ...]
    subscriptions: tuple[ClientSubscription, ...]
    resources: tuple[ManagedResource, ...]


class LayoutStateStore:
    def __init__(self, clients: ClientStore, resources: ResourceStore) -> None:
        self._clients = clients
        self._resources = resources

    async def load_state(self, guild_id: int) -> LayoutState:
        clients = tuple(
            client for client in await self._clients.list_all() if client.guild_id == guild_id
        )
        client_ids = {client.id for client in clients}
        subscriptions = tuple(
            subscription
            for subscription in await self._clients.list_all_subscriptions()
            if subscription.client_id in client_ids
        )
        return LayoutState(
            guild_id=guild_id,
            clients=clients,
            subscriptions=subscriptions,
            resources=await self._resources.list_for_guild(guild_id),
        )


@dataclass(frozen=True)
class Store:
    """The sole application-facing persistence boundary."""

    db: Database
    networks: NetworkStore
    clients: ClientStore
    subscriptions: ClientStore
    blacklists: ClientStore
    relay: RelayStore
    requests: RequestStore
    settings: SettingsStore
    resources: ResourceStore
    layout: LayoutStateStore

    @classmethod
    def create(cls, db: Database) -> Store:
        clients = ClientStore(db)
        resources = ResourceStore(db)
        return cls(
            db=db,
            networks=NetworkStore(db),
            clients=clients,
            subscriptions=clients,
            blacklists=clients,
            relay=RelayStore(db),
            requests=RequestStore(db),
            settings=SettingsStore(db),
            resources=resources,
            layout=LayoutStateStore(clients, resources),
        )
