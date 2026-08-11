from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.core.clients.cache import ClientCache
    from bot.core.database.connection import Database
    from bot.core.database.store import Store
    from bot.core.networks.routing import RoutingService
    from bot.core.settings import BotSettingsService


class Projection(StrEnum):
    NETWORKS = "networks"
    CLIENTS = "clients"
    ROUTING = "routing"


class ProjectionCoordinator:
    """Refresh derived in-memory state once, in dependency order."""

    def __init__(
        self,
        store: Store,
        routing: RoutingService,
        clients: ClientCache,
        settings: Settings,
    ) -> None:
        self._store = store
        self._routing = routing
        self._clients = clients
        self._settings = settings
        self.network_count = 0
        self.client_count = 0
        self.enabled_client_count = 0

    async def refresh(self, projection: Projection) -> None:
        refresh_clients = projection in (Projection.CLIENTS, Projection.ROUTING)
        refresh_networks = projection in (Projection.NETWORKS, Projection.ROUTING)
        if refresh_clients:
            await self._clients.load_cache()
        if refresh_networks:
            await self._routing.load_cache()
            self.network_count = self._routing.network_count
        if refresh_clients:
            clients = await self._store.clients.list_all()
            self.client_count = len(clients)
            self.enabled_client_count = sum(client.enabled for client in clients)


@dataclass
class BotContext:
    settings: Settings
    db: Database
    store: Store
    routing_service: RoutingService
    client_cache: ClientCache
    relay_service: Any
    bot_settings: BotSettingsService
    started_at: datetime
    network_count: int = 0
    client_count: int = 0
    enabled_client_count: int = 0
    projections: ProjectionCoordinator = field(init=False)

    def __post_init__(self) -> None:
        self.projections = ProjectionCoordinator(
            self.store,
            self.routing_service,
            self.client_cache,
            self.settings,
        )

    @classmethod
    def create(
        cls,
        settings: Settings,
        db: Database,
        store: Store,
        routing_service: RoutingService,
        client_cache: ClientCache,
        relay_service: Any,
        bot_settings: BotSettingsService,
    ) -> BotContext:
        return cls(
            settings=settings,
            db=db,
            store=store,
            routing_service=routing_service,
            client_cache=client_cache,
            relay_service=relay_service,
            bot_settings=bot_settings,
            started_at=datetime.now(tz=UTC),
        )

    async def refresh_network_counts(self) -> None:
        await self._refresh(Projection.NETWORKS)

    async def refresh_client_counts(self) -> None:
        await self._refresh(Projection.CLIENTS)

    async def refresh_projections(self) -> None:
        await self._refresh(Projection.ROUTING)

    async def _refresh(self, projection: Projection) -> None:
        await self.projections.refresh(projection)
        self.network_count = self.projections.network_count
        self.client_count = self.projections.client_count
        self.enabled_client_count = self.projections.enabled_client_count

    def uptime_label(self) -> str:
        delta = datetime.now(tz=UTC) - self.started_at
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
