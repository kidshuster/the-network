from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from view_registry_helpers import make_test_view_registry

from bot.domain.errors import NetworkValidationError
from bot.domain.network import Network
from bot.networks.admin import create_network, delete_network
from bot.stickies.network_admin_sticky import build_network_admin_embed


def _mock_context(*, networks: list[Network] | None = None) -> MagicMock:
    context = MagicMock()
    networks = networks or []
    context.network_repo.list_all = AsyncMock(return_value=networks)
    context.client_repo.list_subscriptions_by_network = AsyncMock(return_value=[])
    context.network_repo.create = AsyncMock(
        return_value=Network(
            id=1,
            key="stingers",
            display_name="Stingers",
            feed_category_id=None,
            output_channel_id=None,
            concat_channel_id=None,
            profile_forum_channel_id=None,
            join_channel_id=None,
            enabled=True,
        )
    )
    context.network_repo.get_by_key = AsyncMock(return_value=None)
    context.network_repo.delete = AsyncMock(
        return_value=Network(
            id=1,
            key="stingers",
            display_name="Stingers",
            feed_category_id=None,
            output_channel_id=None,
            concat_channel_id=None,
            profile_forum_channel_id=None,
            join_channel_id=None,
            enabled=True,
        )
    )
    context.client_repo.detach_subscriptions_from_network = AsyncMock()
    context.relay_record_repo.delete_by_network_id = AsyncMock()
    context.server_request_repo.delete_by_network_id = AsyncMock()
    context.routing_service.load_cache = AsyncMock()
    context.client_cache.load_cache = AsyncMock()
    context.refresh_network_counts = AsyncMock()
    return context


@pytest.mark.asyncio
async def test_create_network_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import bot.clients.subscription as client_subscription

    context = _mock_context()
    context.client_repo.list_all = AsyncMock(return_value=[])
    bot = MagicMock()
    bot.settings.network_access_role_name = "The Network"
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    guild.me = MagicMock()
    monkeypatch.setattr(
        "bot.clients.profile_sync.refresh_all_client_profiles",
        AsyncMock(return_value=2),
    )
    monkeypatch.setattr(
        client_subscription,
        "resync_subscriptions_for_network",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "bot.hub.announcements.ensure_hub_announcements_subscription",
        AsyncMock(return_value=False),
    )

    result = await create_network(
        context,
        bot,
        guild,
        key="stingers",
        display_name="Stingers",
        view_registry=make_test_view_registry(),
    )

    assert result.success is True
    assert result.network is not None
    assert result.network.key == "stingers"
    assert result.updated_profile_count == 2


@pytest.mark.asyncio
async def test_create_network_rejects_duplicate_key() -> None:
    existing = Network(
        id=1,
        key="stingers",
        display_name="Stingers",
        feed_category_id=None,
        output_channel_id=None,
        concat_channel_id=None,
        profile_forum_channel_id=None,
        join_channel_id=None,
        enabled=True,
    )
    context = _mock_context()
    context.network_repo.get_by_key = AsyncMock(return_value=existing)
    bot = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100

    result = await create_network(
        context,
        bot,
        guild,
        key="stingers",
        display_name="Stingers",
        view_registry=make_test_view_registry(),
    )

    assert result.success is False
    assert "already exists" in (result.error or "")
    context.network_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_delete_network_hard_deletes_and_detaches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network = Network(
        id=1,
        key="stingers",
        display_name="Stingers",
        feed_category_id=None,
        output_channel_id=None,
        concat_channel_id=None,
        profile_forum_channel_id=None,
        join_channel_id=None,
        enabled=True,
    )
    context = _mock_context(networks=[network])
    context.network_repo.get_by_key = AsyncMock(return_value=network)
    bot = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    monkeypatch.setattr(
        "bot.clients.profile_sync.refresh_all_client_profiles",
        AsyncMock(return_value=1),
    )

    result = await delete_network(
        context, bot, guild, key="stingers", view_registry=make_test_view_registry()
    )

    assert result.success is True
    context.client_repo.detach_subscriptions_from_network.assert_awaited_once_with(
        1,
        "stingers",
    )
    context.relay_record_repo.delete_by_network_id.assert_awaited_once_with(1)
    context.server_request_repo.delete_by_network_id.assert_awaited_once_with(1)
    context.network_repo.delete.assert_awaited_once_with("stingers")


@pytest.mark.asyncio
async def test_create_network_validation_error() -> None:
    context = _mock_context()
    context.network_repo.create = AsyncMock(
        side_effect=NetworkValidationError("duplicate key")
    )
    bot = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100

    result = await create_network(
        context,
        bot,
        guild,
        key="stingers",
        display_name="Stingers",
        view_registry=make_test_view_registry(),
    )

    assert result.success is False
    assert result.error == "duplicate key"


@pytest.mark.asyncio
async def test_delete_network_not_found() -> None:
    context = _mock_context()
    bot = MagicMock()
    guild = MagicMock(spec=discord.Guild)

    result = await delete_network(
        context, bot, guild, key="missing", view_registry=make_test_view_registry()
    )

    assert result.success is False
    assert "not found" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_build_network_admin_embed_lists_networks() -> None:
    network = Network(
        id=1,
        key="alpha",
        display_name="Alpha Net",
        feed_category_id=None,
        output_channel_id=None,
        concat_channel_id=None,
        profile_forum_channel_id=None,
        join_channel_id=None,
        enabled=True,
    )
    context = _mock_context(networks=[network])

    embed = await build_network_admin_embed(context)

    assert embed.title == "Network Administration"
    assert len(embed.fields) == 1
    assert "alpha" in embed.fields[0].name
