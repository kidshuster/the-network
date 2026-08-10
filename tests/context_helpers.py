from __future__ import annotations

from unittest.mock import MagicMock

from bot.clients.cache import ClientCache
from bot.context import BotContext
from bot.db.repositories import (
    ClientRepository,
    NetworkRepository,
    RelayRecordRepository,
    ServerRequestRepository,
    SettingsRepository,
)
from bot.networks.routing import RoutingService


def make_test_context(db) -> BotContext:
    network_repo = NetworkRepository(db)
    client_repo = ClientRepository(db)
    relay_record_repo = RelayRecordRepository(db)
    settings_repo = SettingsRepository(db)
    server_request_repo = ServerRequestRepository(db)
    routing = RoutingService(network_repo, client_repo)
    client_cache = ClientCache(client_repo)
    routing.attach_client_cache(client_cache)
    return BotContext.create(
        settings=MagicMock(),
        db=db,
        network_repo=network_repo,
        client_repo=client_repo,
        relay_record_repo=relay_record_repo,
        routing_service=routing,
        client_cache=client_cache,
        relay_service=MagicMock(),
        bot_settings=MagicMock(),
        settings_repo=settings_repo,
        server_request_repo=server_request_repo,
    )
