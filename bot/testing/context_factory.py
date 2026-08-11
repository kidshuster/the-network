from __future__ import annotations

from bot.app.context import BotContext
from bot.config import Settings
from bot.core.clients.cache import ClientCache
from bot.core.database import migrations
from bot.core.database.connection import Database
from bot.core.database.store import Store
from bot.core.networks.routing import RoutingService
from bot.core.settings import BotSettingsService
from bot.features.recipes.hub.relay.service import RelayService


async def create_bot_context(settings: Settings) -> tuple[Database, BotContext]:
    db = Database(settings.database_path)
    await db.connect()
    await migrations.run_migrations(db)

    store = Store.create(db)
    routing_service = RoutingService(store.networks, store.clients)
    client_cache = ClientCache(store.clients)
    await client_cache.load_cache()
    routing_service.attach_client_cache(client_cache)
    await routing_service.load_cache()

    bot_settings = BotSettingsService(store.settings, settings)
    await bot_settings.load()

    relay_service = RelayService(
        settings,
        routing_service,
        client_cache,
        store.clients,
        store.relay,
    )

    context = BotContext.create(
        settings,
        db,
        store,
        routing_service,
        client_cache,
        relay_service,
        bot_settings,
    )
    context.network_count = routing_service.network_count
    context.client_count = client_cache.client_count
    context.enabled_client_count = client_cache.enabled_client_count
    return db, context
