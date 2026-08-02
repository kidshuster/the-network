from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.db.connection import Database
    from bot.db.repositories import (
        ClientRepository,
        NetworkRepository,
        RelayRecordRepository,
        ServerRequestRepository,
        SettingsRepository,
    )
    from bot.services.bot_settings import BotSettingsService
    from bot.services.client_cache import ClientCache
    from bot.services.relay_service import RelayService
    from bot.services.routing_service import RoutingService


@dataclass
class BotContext:
    settings: Settings
    db: Database
    network_repo: NetworkRepository
    client_repo: ClientRepository
    relay_record_repo: RelayRecordRepository
    routing_service: RoutingService
    client_cache: ClientCache
    relay_service: RelayService
    bot_settings: BotSettingsService
    settings_repo: SettingsRepository
    server_request_repo: ServerRequestRepository
    started_at: datetime
    network_count: int = 0
    client_count: int = 0
    enabled_client_count: int = 0

    @classmethod
    def create(
        cls,
        settings: Settings,
        db: Database,
        network_repo: NetworkRepository,
        client_repo: ClientRepository,
        relay_record_repo: RelayRecordRepository,
        routing_service: RoutingService,
        client_cache: ClientCache,
        relay_service: RelayService,
        bot_settings: BotSettingsService,
        settings_repo: SettingsRepository,
        server_request_repo: ServerRequestRepository,
    ) -> BotContext:
        return cls(
            settings=settings,
            db=db,
            network_repo=network_repo,
            client_repo=client_repo,
            relay_record_repo=relay_record_repo,
            routing_service=routing_service,
            client_cache=client_cache,
            relay_service=relay_service,
            bot_settings=bot_settings,
            settings_repo=settings_repo,
            server_request_repo=server_request_repo,
            started_at=datetime.now(tz=UTC),
        )

    async def refresh_network_counts(self) -> None:
        await self.routing_service.load_cache()
        self.network_count = self.routing_service.network_count

    async def refresh_client_counts(self) -> None:
        await self.client_cache.load_cache()
        self.client_count = self.client_cache.client_count
        self.enabled_client_count = self.client_cache.enabled_client_count

    def uptime_label(self) -> str:
        delta = datetime.now(tz=UTC) - self.started_at
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
