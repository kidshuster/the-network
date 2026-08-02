from __future__ import annotations

from bot.config import Settings
from bot.context import BotContext
from bot.db import migrations
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


async def create_bot_context(settings: Settings) -> tuple[Database, BotContext]:
    db = Database(settings.database_path)
    await db.connect()
    await migrations.run_migrations(db)

    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    relay_record_repo = RelayRecordRepository(db)
    routing_service = RoutingService(network_repo, client_repo)
    client_cache = ClientCache(client_repo)
    await client_cache.load_cache()
    routing_service.attach_client_cache(client_cache)
    await routing_service.load_cache()

    settings_repo = SettingsRepository(db)
    server_request_repo = ServerRequestRepository(db)
    bot_settings = BotSettingsService(settings_repo, settings)
    await bot_settings.load()

    relay_service = RelayService(
        settings,
        routing_service,
        client_cache,
        client_repo,
        relay_record_repo,
    )

    context = BotContext.create(
        settings,
        db,
        network_repo,
        client_repo,
        relay_record_repo,
        routing_service,
        client_cache,
        relay_service,
        bot_settings,
        settings_repo,
        server_request_repo,
    )
    context.network_count = routing_service.network_count
    context.client_count = client_cache.client_count
    context.enabled_client_count = client_cache.enabled_client_count
    return db, context
