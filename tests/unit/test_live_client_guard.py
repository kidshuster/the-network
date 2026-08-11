from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from tests.live.client_guard import (
    assert_protected_clients_unchanged,
    snapshot_protected_clients,
)


def _client(client_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=client_id,
        guild_id=1,
        server_name=name,
        client_role_id=client_id + 100,
        category_id=client_id + 200,
        profile_channel_id=client_id + 300,
    )


@pytest.mark.asyncio
async def test_protected_snapshot_excludes_smoke_clients() -> None:
    production = _client(1, "Production Client")
    smoke = _client(2, "Smoke Accept abc123")
    context = SimpleNamespace(
        store=SimpleNamespace(
            clients=SimpleNamespace(
                list_all=AsyncMock(return_value=[production, smoke]),
                list_subscriptions_by_client=AsyncMock(return_value=[]),
            )
        )
    )

    snapshot = await snapshot_protected_clients(context, guild_id=1)

    assert [client.server_name for client in snapshot] == ["Production Client"]


@pytest.mark.asyncio
async def test_protected_guard_detects_database_deletion() -> None:
    production = _client(1, "Production Client")
    clients = SimpleNamespace(
        list_all=AsyncMock(return_value=[production]),
        list_subscriptions_by_client=AsyncMock(return_value=[]),
        get_by_id=AsyncMock(return_value=None),
    )
    context = SimpleNamespace(store=SimpleNamespace(clients=clients))
    snapshot = await snapshot_protected_clients(context, guild_id=1)
    guild = MagicMock(spec=discord.Guild)

    with pytest.raises(RuntimeError, match="database record deleted"):
        await assert_protected_clients_unchanged(
            guild,
            context,
            snapshot,
            phase="test phase",
        )


@pytest.mark.asyncio
async def test_protected_guard_accepts_unchanged_discord_resources() -> None:
    production = _client(1, "Production Client")
    clients = SimpleNamespace(
        list_all=AsyncMock(return_value=[production]),
        list_subscriptions_by_client=AsyncMock(return_value=[]),
        get_by_id=AsyncMock(return_value=production),
    )
    context = SimpleNamespace(store=SimpleNamespace(clients=clients))
    category = MagicMock(spec=discord.CategoryChannel)
    profile = MagicMock(spec=discord.TextChannel)
    role = MagicMock(spec=discord.Role)
    guild = MagicMock(spec=discord.Guild)
    guild.get_role.return_value = role
    guild.get_channel.side_effect = lambda resource_id: (
        category if resource_id == production.category_id else profile
    )
    snapshot = await snapshot_protected_clients(context, guild_id=1)

    await assert_protected_clients_unchanged(
        guild,
        context,
        snapshot,
        phase="test phase",
    )


@pytest.mark.asyncio
async def test_protected_guard_accepts_relinked_subscription_with_new_row_id() -> None:
    production = _client(1, "Production Client")
    original = SimpleNamespace(
        id=10,
        network_key="network-a",
        publish_channel_id=401,
        subscribe_channel_id=402,
    )
    recreated = SimpleNamespace(
        id=11,
        network_key="network-a",
        publish_channel_id=401,
        subscribe_channel_id=402,
    )
    clients = SimpleNamespace(
        list_all=AsyncMock(return_value=[production]),
        list_subscriptions_by_client=AsyncMock(side_effect=[[original], [recreated]]),
        get_by_id=AsyncMock(return_value=production),
    )
    context = SimpleNamespace(store=SimpleNamespace(clients=clients))
    role = MagicMock(spec=discord.Role)
    category = MagicMock(spec=discord.CategoryChannel)
    text_channel = MagicMock(spec=discord.TextChannel)
    guild = MagicMock(spec=discord.Guild)
    guild.get_role.return_value = role
    guild.get_channel.side_effect = lambda resource_id: (
        category if resource_id == production.category_id else text_channel
    )

    snapshot = await snapshot_protected_clients(context, guild_id=1)
    await assert_protected_clients_unchanged(
        guild,
        context,
        snapshot,
        phase="network rebuild",
    )
