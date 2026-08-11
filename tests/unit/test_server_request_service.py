from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from request_helpers import make_server_request
from view_registry_helpers import make_test_view_registry

from bot.core.models.server_request import ServerRequestStatus
from bot.features.recipes.hub.onboarding.service import ServerRequestService


def _service_context(**repo_methods: object) -> SimpleNamespace:
    repo = SimpleNamespace(**repo_methods)
    store = SimpleNamespace(
        requests=repo,
        clients=SimpleNamespace(get_by_server_name=AsyncMock(return_value=None)),
    )
    return SimpleNamespace(
        store=store,
        client_cache=SimpleNamespace(load_cache=AsyncMock()),
        refresh_projections=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_submit_request_rejects_duplicate_pending() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    context = _service_context(
        get_pending_for_requester=AsyncMock(return_value=make_server_request()),
    )
    bot = MagicMock()
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())  # type: ignore[arg-type]

    requester = MagicMock(spec=discord.User, id=555)
    attachment = MagicMock(spec=discord.Attachment)

    result = await service.submit_request(
        guild,
        requester=requester,
        server_name="Beta",
        profile_image=attachment,
    )

    assert result.success is False
    assert "pending" in (result.error or "").casefold()


@pytest.mark.asyncio
async def test_submit_request_rejects_existing_client_name() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    context = _service_context(
        get_pending_for_requester=AsyncMock(return_value=None),
    )
    context.store.clients.get_by_server_name = AsyncMock(return_value=MagicMock())
    bot = MagicMock()
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())  # type: ignore[arg-type]

    requester = MagicMock(spec=discord.User, id=555)
    attachment = MagicMock(spec=discord.Attachment)

    result = await service.submit_request(
        guild,
        requester=requester,
        server_name="Acme",
        profile_image=attachment,
    )

    assert result.success is False
    assert "already exists" in (result.error or "")


@pytest.mark.asyncio
async def test_approve_request_rejects_already_reviewed() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    context = _service_context(
        get_by_id=AsyncMock(return_value=make_server_request(status=ServerRequestStatus.APPROVED)),
    )
    bot = MagicMock()
    bot.settings.guild_id = 100
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())  # type: ignore[arg-type]
    moderator = MagicMock(spec=discord.Member, id=1)

    result = await service.approve_request(guild, request_id=7, moderator=moderator)

    assert result.success is False
    assert "already reviewed" in (result.error or "").casefold()


@pytest.mark.asyncio
async def test_approve_request_provisions_client_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    guild.me = bot_member
    request = make_server_request()
    context = _service_context(
        get_by_id=AsyncMock(return_value=request),
        resolve=AsyncMock(),
    )

    client_role = MagicMock(spec=discord.Role, id=601)
    profile = MagicMock(spec=discord.TextChannel, id=602, mention="#acme-profile")
    provision_outcome = MagicMock(
        success=True,
        client_role=client_role,
        profile_channel=profile,
        error=None,
    )

    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service._load_request_profile_image",
        AsyncMock(return_value=MagicMock(data=b"png")),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_provision_client_from_request",
        AsyncMock(return_value=provision_outcome),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_finalize_review_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_notify_requester",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.leaders.grant_leaders_channel_access",
        AsyncMock(),
    )

    requester = MagicMock(spec=discord.Member, id=555)
    requester.add_roles = AsyncMock()
    guild.get_member = MagicMock(return_value=requester)

    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.settings.network_access_role_name = "The Network"
    bot.settings.network_operator_role_name = "The Network+"
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())  # type: ignore[arg-type]
    moderator = MagicMock(spec=discord.Member, id=1)

    result = await service.approve_request(guild, request_id=7, moderator=moderator)

    assert result.success is True
    context.store.requests.resolve.assert_awaited_once()
    requester.add_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_request_grants_leaders_access_for_provisioned_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    guild.me = bot_member
    request = make_server_request()
    context = _service_context(
        get_by_id=AsyncMock(return_value=request),
        resolve=AsyncMock(),
    )

    client_role = MagicMock(spec=discord.Role, id=601)
    profile = MagicMock(spec=discord.TextChannel, id=602, mention="#acme-profile")
    provision_outcome = MagicMock(
        success=True,
        client_role=client_role,
        profile_channel=profile,
        error=None,
    )
    grant_mock = AsyncMock(return_value=MagicMock(failures=[]))

    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service._load_request_profile_image",
        AsyncMock(return_value=MagicMock(data=b"png")),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_provision_client_from_request",
        AsyncMock(return_value=provision_outcome),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_finalize_review_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_notify_requester",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.leaders.grant_leaders_channel_access",
        grant_mock,
    )

    requester = MagicMock(spec=discord.Member, id=555)
    requester.add_roles = AsyncMock()
    guild.get_member = MagicMock(return_value=requester)

    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.settings.network_access_role_name = "The Network"
    bot.settings.network_operator_role_name = "The Network+"
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())  # type: ignore[arg-type]
    moderator = MagicMock(spec=discord.Member, id=1)

    result = await service.approve_request(guild, request_id=7, moderator=moderator)

    assert result.success is True
    grant_mock.assert_awaited_once()
    grant_call = grant_mock.await_args
    assert grant_call is not None
    assert grant_call.args[3] is client_role
    assert grant_call.kwargs["access_role_name"] == "The Network"


@pytest.mark.asyncio
async def test_approve_request_surfaces_leaders_sync_failures_in_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    guild.me = bot_member
    request = make_server_request()
    context = _service_context(
        get_by_id=AsyncMock(return_value=request),
        resolve=AsyncMock(),
    )

    client_role = MagicMock(spec=discord.Role, id=601)
    profile = MagicMock(spec=discord.TextChannel, id=602, mention="#acme-profile")
    provision_outcome = MagicMock(
        success=True,
        client_role=client_role,
        profile_channel=profile,
        error=None,
    )

    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service._load_request_profile_image",
        AsyncMock(return_value=MagicMock(data=b"png")),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_provision_client_from_request",
        AsyncMock(return_value=provision_outcome),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_finalize_review_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_notify_requester",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.leaders.grant_leaders_channel_access",
        AsyncMock(
            return_value=MagicMock(
                failures=["Leaders category not found — run `/server init` first"],
            ),
        ),
    )

    requester = MagicMock(spec=discord.Member, id=555)
    requester.add_roles = AsyncMock()
    guild.get_member = MagicMock(return_value=requester)

    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.settings.network_access_role_name = "The Network"
    bot.settings.network_operator_role_name = "The Network+"
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())  # type: ignore[arg-type]
    moderator = MagicMock(spec=discord.Member, id=1)

    result = await service.approve_request(guild, request_id=7, moderator=moderator)

    assert result.success is True
    assert result.message is not None
    assert "Leaders access sync reported issues" in result.message
    assert "Leaders category not found" in result.message


@pytest.mark.asyncio
async def test_approve_request_surfaces_provisioning_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    guild.me = bot_member
    request = make_server_request()
    context = _service_context(
        get_by_id=AsyncMock(return_value=request),
    )

    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service._load_request_profile_image",
        AsyncMock(return_value=MagicMock(data=b"png")),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_provision_client_from_request",
        AsyncMock(return_value=MagicMock(success=False, error="Missing Permissions")),
    )

    bot = MagicMock()
    bot.settings.guild_id = 100
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())  # type: ignore[arg-type]
    moderator = MagicMock(spec=discord.Member, id=1)

    result = await service.approve_request(guild, request_id=7, moderator=moderator)

    assert result.success is False
    assert "Missing Permissions" in (result.error or "")


@pytest.mark.asyncio
async def test_deny_request_resolves_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    request = make_server_request()
    context = _service_context(
        get_by_id=AsyncMock(return_value=request),
        resolve=AsyncMock(),
    )

    monkeypatch.setattr(
        ServerRequestService,
        "_finalize_review_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        ServerRequestService,
        "_notify_requester",
        AsyncMock(),
    )

    requester = MagicMock(spec=discord.User, id=555)
    guild.get_member = MagicMock(return_value=requester)

    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.get_guild = MagicMock(return_value=guild)
    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())  # type: ignore[arg-type]
    moderator = MagicMock(spec=discord.Member, id=1)

    result = await service.deny_request(request_id=7, moderator=moderator)

    assert result.success is True
    context.store.requests.resolve.assert_awaited_once()
    resolve_kwargs = context.store.requests.resolve.await_args.kwargs
    assert resolve_kwargs["status"] == ServerRequestStatus.DENIED
