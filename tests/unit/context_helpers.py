from __future__ import annotations

from unittest.mock import MagicMock

from bot.app.context import BotContext
from bot.core.clients.cache import ClientCache
from bot.core.database.store import Store
from bot.core.networks.routing import RoutingService


def make_test_context(db) -> BotContext:
    store = Store.create(db)
    routing = RoutingService(store.networks, store.clients)
    client_cache = ClientCache(store.clients)
    routing.attach_client_cache(client_cache)
    return BotContext.create(
        settings=MagicMock(),
        db=db,
        store=store,
        routing_service=routing,
        client_cache=client_cache,
        relay_service=MagicMock(),
        bot_settings=MagicMock(),
    )
