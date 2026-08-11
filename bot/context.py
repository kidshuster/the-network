from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.bot_settings import BotSettingsService
    from bot.clients.cache import ClientCache
    from bot.config import Settings
    from bot.db.connection import Database
    from bot.db.store import Store
    from bot.networks.routing import RoutingService
    from bot.relay.service import RelayService


@dataclass
class BotContext:
    settings: Settings
    db: Database
    store: Store
    routing_service: RoutingService
    client_cache: ClientCache
    relay_service: RelayService
    bot_settings: BotSettingsService
    started_at: datetime
    network_count: int = 0
    client_count: int = 0
    enabled_client_count: int = 0

    @classmethod
    def create(
        cls,
        settings: Settings,
        db: Database,
        store: Store,
        routing_service: RoutingService,
        client_cache: ClientCache,
        relay_service: RelayService,
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
        await self.routing_service.load_cache()
        self.network_count = self.routing_service.network_count

    async def refresh_client_counts(self) -> None:
        await self.client_cache.load_cache()
        from bot.hub.announcements import is_hub_announcements_client

        clients = await self.store.clients.list_all()
        visible = [
            client
            for client in clients
            if not is_hub_announcements_client(client, self.settings)
        ]
        self.client_count = len(visible)
        self.enabled_client_count = sum(1 for client in visible if client.enabled)

    def uptime_label(self) -> str:
        delta = datetime.now(tz=UTC) - self.started_at
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
