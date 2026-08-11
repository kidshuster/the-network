from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from view_registry_helpers import make_test_view_registry

from bot.clients.reconnect import reconnect_clients_on_init
from bot.domain.client import Client
from bot.hub.init import GuildInitResult


def _stored_client(*, guild_id: int = 100, client_id: int = 1) -> Client:
    return Client(
        id=client_id,
        guild_id=guild_id,
        server_name="Acme",
        display_name="Acme",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        timecode_enabled=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


@pytest.mark.asyncio
async def test_reconnect_clients_rectifies_and_refreshes_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, human_mod, access, _ = make_guild_with_roles()
    client = _stored_client()

    category = MagicMock(spec=discord.CategoryChannel, id=10)
    guild.get_channel = MagicMock(return_value=category)

    rectified = MagicMock()
    rectified.synced = ["category", "#acme-profile"]
    rectified.skipped = []
    rectified.failures = []
    rectified.rectification_notes.return_value = ["**Acme**: rectified category, #acme-profile."]
    rectified.skip_notes.return_value = []
    rectified.failure_notes.return_value = []

    monkeypatch.setattr(
        "bot.clients.reconnect.rectify_client_permissions",
        AsyncMock(return_value=rectified),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.sync_client_channel_names",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.sync_subscription_setup",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.reorder_client_category_channels",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.refresh_client_profile_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.resync_subscriptions_for_network",
        AsyncMock(return_value=0),
    )

    bot = MagicMock()
    bot.settings.network_access_role_name = "The Network"
    bot.add_view = MagicMock()
    context = MagicMock()
    context.store.clients.list_subscriptions_by_client = AsyncMock(return_value=[])
    context.store.networks.list_all = AsyncMock(return_value=[])

    view_registry = make_test_view_registry()
    result = GuildInitResult(success=True)
    await reconnect_clients_on_init(
        guild,
        bot,
        context,
        bot_member,
        access,
        human_mod,
        [client],
        result=result,
        access_role_name="The Network",
        view_registry=view_registry,
    )

    assert any("rectified" in note for note in result.rectifications)
    assert any("refreshed" in note for note in result.rectifications)
    view_registry.register_client_profile_for_client.assert_called_once()


@pytest.mark.asyncio
async def test_reconnect_skips_post_rectify_when_client_missing_in_discord(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, human_mod, access, _ = make_guild_with_roles()
    client = _stored_client()

    rectified = MagicMock()
    rectified.synced = []
    rectified.skipped = ["category missing in Discord"]
    rectified.failures = []
    rectified.rectification_notes.return_value = []
    rectified.skip_notes.return_value = ["**Acme**: category missing in Discord"]
    rectified.failure_notes.return_value = []

    monkeypatch.setattr(
        "bot.clients.reconnect.rectify_client_permissions",
        AsyncMock(return_value=rectified),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.sync_client_channel_names",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.refresh_client_profile_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.resync_subscriptions_for_network",
        AsyncMock(return_value=0),
    )

    bot = MagicMock()
    bot.settings.network_access_role_name = "The Network"
    bot.add_view = MagicMock()
    context = MagicMock()
    context.store.networks.list_all = AsyncMock(return_value=[])

    view_registry = make_test_view_registry()
    result = GuildInitResult(success=True)
    await reconnect_clients_on_init(
        guild,
        bot,
        context,
        bot_member,
        access,
        human_mod,
        [client],
        result=result,
        view_registry=view_registry,
    )

    assert result.rectification_skipped
    view_registry.register_client_profile_for_client.assert_not_called()


@pytest.mark.asyncio
async def test_reconnect_records_failure_when_post_rectify_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, human_mod, access, _ = make_guild_with_roles()
    client = _stored_client()
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    guild.get_channel = MagicMock(return_value=category)

    rectified = MagicMock()
    rectified.synced = ["category"]
    rectified.skipped = []
    rectified.failures = []
    rectified.rectification_notes.return_value = ["**Acme**: rectified category."]
    rectified.skip_notes.return_value = []
    rectified.failure_notes.return_value = []

    monkeypatch.setattr(
        "bot.clients.reconnect.rectify_client_permissions",
        AsyncMock(return_value=rectified),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.sync_client_channel_names",
        AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Missing Permissions")),
    )
    monkeypatch.setattr(
        "bot.clients.reconnect.resync_subscriptions_for_network",
        AsyncMock(return_value=0),
    )

    bot = MagicMock()
    bot.settings.network_access_role_name = "The Network"
    context = MagicMock()
    context.store.clients.list_subscriptions_by_client = AsyncMock(return_value=[])
    context.store.networks.list_all = AsyncMock(return_value=[])

    view_registry = make_test_view_registry()
    result = GuildInitResult(success=True)
    await reconnect_clients_on_init(
        guild,
        bot,
        context,
        bot_member,
        access,
        human_mod,
        [client],
        result=result,
        view_registry=view_registry,
    )

    assert any("could not finish reconnect" in note for note in result.rectification_failures)


@pytest.mark.asyncio
async def test_reconnect_no_clients_adds_skip_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, human_mod, access, _ = make_guild_with_roles()
    bot = MagicMock()
    context = MagicMock()
    result = GuildInitResult(success=True)

    view_registry = make_test_view_registry()
    await reconnect_clients_on_init(
        guild,
        bot,
        context,
        bot_member,
        access,
        human_mod,
        [],
        result=result,
        view_registry=view_registry,
    )

    assert any("none registered" in note for note in result.rectifications)
