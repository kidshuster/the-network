from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from request_helpers import make_server_request
from view_registry_helpers import make_test_view_registry
from widget_helpers import wire_widget_bot

from bot.app.context import BotContext
from bot.app.widgets import render_view
from bot.core.clients.cache import ClientCache
from bot.core.clients.integrity import ClientIntegrity, inspect_client_integrity
from bot.core.database.store import Store
from bot.core.models.client import Client
from bot.core.models.server_request import ServerRequestStatus
from bot.core.networks.routing import RoutingService
from bot.features.recipes.hub.clients.deletion import delete_client_resources
from bot.features.recipes.hub.onboarding.service import ServerRequestService


def _client(**overrides: object) -> Client:
    defaults: dict[str, object] = {
        "id": 1,
        "guild_id": 100,
        "server_name": "Test",
        "display_name": "Test",
        "category_id": 10,
        "client_role_id": 11,
        "profile_channel_id": 30,
        "profile_message_id": 40,
        "enabled": True,
        "timecode_enabled": True,
        "emoji_id": None,
        "emoji_name": None,
        "image_hash": None,
        "degraded_reason": None,
    }
    defaults.update(overrides)
    return Client(**defaults)  # type: ignore[arg-type]


def _make_context(db) -> BotContext:
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


@pytest.mark.asyncio
async def test_inspect_client_integrity_healthy() -> None:
    guild = MagicMock(spec=discord.Guild)
    role = MagicMock(spec=discord.Role)
    category = MagicMock(spec=discord.CategoryChannel)
    profile = MagicMock(spec=discord.TextChannel)
    guild.get_role = MagicMock(return_value=role)
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {10: category, 30: profile}.get(channel_id)
    )

    integrity = await inspect_client_integrity(guild, _client())
    assert integrity.is_healthy is True


@pytest.mark.asyncio
async def test_inspect_client_integrity_missing_category() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.get_role = MagicMock(return_value=MagicMock(spec=discord.Role))
    guild.get_channel = MagicMock(return_value=None)
    guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "missing"))
    guild.fetch_role = AsyncMock(return_value=MagicMock(spec=discord.Role))

    integrity = await inspect_client_integrity(guild, _client())
    assert integrity.is_healthy is False
    assert integrity.category_present is False
    assert integrity.profile_channel_present is False


@pytest.mark.asyncio
async def test_submit_creates_repair_request_for_malformed_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    guild.me = bot_member
    existing = _client(id=9, server_name="Test")
    created = make_server_request(repair_client_id=9, server_name="Test")

    requests = SimpleNamespace(
        get_pending_for_requester=AsyncMock(return_value=None),
        get_pending_for_repair_client=AsyncMock(return_value=None),
        create=AsyncMock(return_value=created),
        set_moderator_message_id=AsyncMock(return_value=created),
    )
    clients = SimpleNamespace(
        get_by_server_name=AsyncMock(return_value=existing),
        list_subscriptions_by_client=AsyncMock(return_value=[]),
    )
    context = SimpleNamespace(
        store=SimpleNamespace(requests=requests, clients=clients),
        refresh_projections=AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.core.clients.integrity.inspect_client_integrity",
        AsyncMock(return_value=ClientIntegrity(False, False, False)),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service.read_profile_image_attachment",
        AsyncMock(return_value=MagicMock(data=b"png")),
    )
    channel = MagicMock()
    channel.permissions_for.return_value = MagicMock(
        view_channel=True, send_messages=True, embed_links=True
    )
    channel.send = AsyncMock(return_value=MagicMock(id=9001))
    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service.resolve_hub_category",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service.resolve_hub_channel",
        MagicMock(return_value=channel),
    )
    monkeypatch.setattr(
        "bot.features.channels.resolve.resolve_human_moderator_role",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.core.relay.delivery.build_moderator_join_request_send_kwargs",
        MagicMock(return_value={}),
    )

    bot = MagicMock()
    bot.settings.guild_id = 100
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())
    attachment = MagicMock(spec=discord.Attachment, url="https://example.com/p.png")

    result = await service.submit_request(
        guild,
        requester=MagicMock(spec=discord.User, id=555, mention="@user"),
        server_name="Test",
        profile_image=attachment,
    )

    assert result.success is True
    create_kwargs = requests.create.await_args.kwargs
    assert create_kwargs["repair_client_id"] == 9


@pytest.mark.asyncio
async def test_deny_repair_request_force_deletes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    guild.me = bot_member
    request = make_server_request(repair_client_id=9)
    client = _client(id=9, server_name="Test")
    context = SimpleNamespace(
        store=SimpleNamespace(
            requests=SimpleNamespace(
                get_by_id=AsyncMock(return_value=request),
                resolve=AsyncMock(),
            ),
            clients=SimpleNamespace(get_by_id=AsyncMock(return_value=client)),
            networks=MagicMock(),
        ),
        refresh_projections=AsyncMock(),
    )
    delete_mock = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.deletion.delete_client_resources",
        delete_mock,
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_finalize_review_message",
        AsyncMock(),
    )
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())

    result = await service.deny_request(
        request_id=7,
        moderator=MagicMock(spec=discord.Member, id=1),
    )

    assert result.success is True
    assert "removed remaining resources" in (result.message or "")
    delete_mock.assert_awaited_once()
    assert delete_mock.await_args.kwargs["force"] is True


@pytest.mark.asyncio
async def test_force_delete_continues_when_unsubscribe_fails(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _make_context(db)
    network = await context.store.networks.create(
        guild_id=100, key="stingers", display_name="Stingers"
    )
    client = await context.store.clients.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    await context.store.clients.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=203,
        subscribe_channel_id=202,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.unsubscribe_client",
        AsyncMock(return_value=MagicMock(success=False, error="Missing Permissions")),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.deletion.purge_client_discord_resources",
        AsyncMock(),
    )
    guild = MagicMock(spec=discord.Guild)
    guild.me = MagicMock(spec=discord.Member)
    context.refresh_projections = AsyncMock()

    result = await delete_client_resources(
        guild,
        guild.me,
        client=client,
        client_repo=context.store.clients,
        network_repo=context.store.networks,
        context=context,
        force=True,
    )

    assert result.success is True
    assert await context.store.clients.get_by_id(client.id) is None


@pytest.mark.asyncio
async def test_update_provisioned_resources_keeps_client_id(db) -> None:
    context = _make_context(db)
    client = await context.store.clients.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    updated = await context.store.clients.update_provisioned_resources(
        client.id,
        category_id=110,
        client_role_id=111,
        profile_channel_id=130,
        profile_message_id=140,
        display_name="Acme Fixed",
    )
    assert updated.id == client.id
    assert updated.category_id == 110
    assert updated.display_name == "Acme Fixed"


def test_network_admin_binds_delete_client_button() -> None:
    bot = wire_widget_bot()
    view = render_view("network_admin", bot)
    labels = {
        child.label for child in view.children if isinstance(child, discord.ui.Button)
    }
    assert "Delete Client" in labels


@pytest.mark.asyncio
async def test_approve_repair_uses_reconcile_not_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    guild.me = bot_member
    request = make_server_request(repair_client_id=9)
    context = SimpleNamespace(
        store=SimpleNamespace(
            requests=SimpleNamespace(
                get_by_id=AsyncMock(return_value=request),
                resolve=AsyncMock(),
            ),
            clients=MagicMock(),
            networks=MagicMock(),
        ),
        refresh_projections=AsyncMock(),
    )
    role = MagicMock(spec=discord.Role)
    profile = MagicMock(spec=discord.TextChannel, mention="#test-profile")
    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service._load_request_profile_image",
        AsyncMock(return_value=MagicMock(data=b"png")),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_provision_client_from_request",
        AsyncMock(
            return_value=SimpleNamespace(
                success=True, client_role=role, profile_channel=profile, error=None
            )
        ),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_finalize_review_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.leaders.grant_leaders_channel_access",
        AsyncMock(return_value=MagicMock(failures=[])),
    )
    guild.get_member = MagicMock(return_value=None)
    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.settings.network_access_role_name = "The Network"
    bot.settings.network_operator_role_name = "The Network+"
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())

    result = await service.approve_request(
        guild,
        request_id=7,
        moderator=MagicMock(spec=discord.Member, id=1),
    )

    assert result.success is True
    assert "Repaired" in (result.message or "")
    assert request.status == ServerRequestStatus.PENDING  # status change is via resolve
    context.store.requests.resolve.assert_awaited_once()
