from __future__ import annotations

from bot.db.repositories import ClientRepository, NetworkRepository
from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.domain.network import Network


async def create_test_network(
    repo: NetworkRepository,
    *,
    key: str = "stingers",
    display_name: str = "Stingers",
    guild_id: int = 100,
) -> Network:
    return await repo.create(
        guild_id=guild_id,
        key=key,
        display_name=display_name,
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )


async def create_test_client(
    repo: ClientRepository,
    *,
    guild_id: int = 100,
    server_name: str = "Acme",
    display_name: str = "Acme",
    category_id: int = 10,
    client_role_id: int = 20,
    profile_channel_id: int = 30,
    profile_message_id: int = 40,
) -> Client:
    return await repo.create(
        guild_id=guild_id,
        server_name=server_name,
        display_name=display_name,
        category_id=category_id,
        client_role_id=client_role_id,
        profile_channel_id=profile_channel_id,
        profile_message_id=profile_message_id,
    )


async def create_test_subscription(
    client_repo: ClientRepository,
    *,
    client: Client,
    network: Network,
    publish_channel_id: int = 100,
    subscribe_channel_id: int = 101,
) -> ClientSubscription:
    return await client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=publish_channel_id,
        subscribe_channel_id=subscribe_channel_id,
    )
