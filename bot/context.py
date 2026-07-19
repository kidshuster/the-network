from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.db.connection import Database
    from bot.db.repositories import (
        NetworkRepository,
        ProfileRepository,
        RelayRecordRepository,
        ServerRequestRepository,
        SettingsRepository,
    )
    from bot.services.bot_settings import BotSettingsService
    from bot.services.network_cleanup import NetworkCleanupService
    from bot.services.profile_cache import ProfileCache
    from bot.services.profile_cleanup import ProfileCleanupService
    from bot.services.profile_sync import ProfileSyncService
    from bot.services.relay_service import RelayService
    from bot.services.routing_service import RoutingService


@dataclass
class BotContext:
    settings: Settings
    db: Database
    network_repo: NetworkRepository
    profile_repo: ProfileRepository
    relay_record_repo: RelayRecordRepository
    routing_service: RoutingService
    profile_cache: ProfileCache
    profile_sync: ProfileSyncService
    profile_cleanup: ProfileCleanupService
    network_cleanup: NetworkCleanupService
    relay_service: RelayService
    bot_settings: BotSettingsService
    settings_repo: SettingsRepository
    server_request_repo: ServerRequestRepository
    started_at: datetime
    network_count: int = 0
    profile_count: int = 0
    enabled_profile_count: int = 0

    @classmethod
    def create(
        cls,
        settings: Settings,
        db: Database,
        network_repo: NetworkRepository,
        profile_repo: ProfileRepository,
        relay_record_repo: RelayRecordRepository,
        routing_service: RoutingService,
        profile_cache: ProfileCache,
        profile_sync: ProfileSyncService,
        profile_cleanup: ProfileCleanupService,
        network_cleanup: NetworkCleanupService,
        relay_service: RelayService,
        bot_settings: BotSettingsService,
        settings_repo: SettingsRepository,
        server_request_repo: ServerRequestRepository,
    ) -> BotContext:
        return cls(
            settings=settings,
            db=db,
            network_repo=network_repo,
            profile_repo=profile_repo,
            relay_record_repo=relay_record_repo,
            routing_service=routing_service,
            profile_cache=profile_cache,
            profile_sync=profile_sync,
            profile_cleanup=profile_cleanup,
            network_cleanup=network_cleanup,
            relay_service=relay_service,
            bot_settings=bot_settings,
            settings_repo=settings_repo,
            server_request_repo=server_request_repo,
            started_at=datetime.now(tz=UTC),
        )

    async def refresh_network_counts(self) -> None:
        await self.routing_service.load_cache()
        self.network_count = self.routing_service.network_count

    async def refresh_profile_counts(self) -> None:
        await self.profile_cache.load_cache()
        self.profile_count = self.profile_cache.profile_count
        self.enabled_profile_count = self.profile_cache.enabled_profile_count

    def uptime_label(self) -> str:
        delta = datetime.now(tz=UTC) - self.started_at
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
