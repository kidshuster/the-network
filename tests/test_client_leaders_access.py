from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.permissions.service import build_context, permission_service


def _channel_sync_setup(*, category_id: int = 100) -> tuple[MagicMock, MagicMock, MagicMock]:
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.guild = guild
    channel.id = 1
    channel.category_id = category_id
    channel.overwrites = {}
    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild = guild
    bot_member.guild_permissions.manage_channels = True
    bot_member.top_role = MagicMock(position=10, id=50)
    return guild, channel, bot_member


def test_client_approval_grants_leaders_channel_access() -> None:
    from bot.onboarding.server_requests import ServerRequestService

    source = inspect.getsource(ServerRequestService.approve_request)
    assert "grant_leaders_channel_access" in source


def test_guild_init_uses_layout_batch() -> None:
    from bot.hub.init import initialize_guild

    source = inspect.getsource(initialize_guild)
    assert "compile_hub" in source
    assert "apply_layout" in source


@pytest.mark.asyncio
async def test_ensure_text_omits_sync_permissions_on_create() -> None:
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 900
    channel.category_id = 100
    channel.overwrites = {}
    channel.edit = AsyncMock()
    guild.create_text_channel = AsyncMock(return_value=channel)

    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild = guild
    bot_member.guild_permissions.manage_channels = True
    bot_member.top_role = MagicMock(position=10, id=50)
    category = MagicMock(spec=discord.CategoryChannel, id=100)

    with patch(
        "bot.hub.notifications.ensure_guild_only_mention_notifications",
        new=AsyncMock(),
    ):
        await permission_service.ensure_text_channel(
            guild,
            build_context(guild, bot_member, access_role=None, moderator_role=None),
            existing=None,
            name="probe-profile",
            category=category,
            overwrites={everyone: discord.PermissionOverwrite(view_channel=False)},
            reason="test",
        )

    assert "sync_permissions" not in guild.create_text_channel.await_args.kwargs
    assert "overwrites" not in guild.create_text_channel.await_args.kwargs


@pytest.mark.asyncio
async def test_reconcile_map_bulk_edit() -> None:
    _, channel, bot_member = _channel_sync_setup()
    channel.edit = AsyncMock()
    client_role = MagicMock(spec=discord.Role, id=101, position=1)
    client_role.is_default.return_value = False
    overwrite = discord.PermissionOverwrite(view_channel=True)

    await permission_service.reconcile_map(
        channel,
        build_context(channel.guild, bot_member, access_role=None, moderator_role=None),
        {client_role: overwrite},
        reason="test",
    )
    channel.edit.assert_awaited_once_with(
        overwrites={client_role: overwrite},
        sync_permissions=False,
        reason="test",
    )


@pytest.mark.asyncio
async def test_reconcile_map_falls_back_to_incremental() -> None:
    _, channel, bot_member = _channel_sync_setup()
    channel.edit = AsyncMock(
        side_effect=[
            discord.HTTPException(MagicMock(), "Forbidden"),
            None,
            discord.HTTPException(MagicMock(), "Forbidden"),
        ]
    )
    channel.set_permissions = AsyncMock()
    client_role = MagicMock(spec=discord.Role, id=101, position=1)
    client_role.is_default.return_value = False
    overwrite = discord.PermissionOverwrite(view_channel=True)

    await permission_service.reconcile_map(
        channel,
        build_context(channel.guild, bot_member, access_role=None, moderator_role=None),
        {client_role: overwrite},
        reason="test",
    )
    channel.set_permissions.assert_awaited_once_with(
        client_role,
        overwrite=overwrite,
        reason="test",
    )


@pytest.mark.asyncio
async def test_grant_leaders_channel_access_runs_ensure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bot.hub.leaders import LeadersSyncResult, grant_leaders_channel_access

    guild = MagicMock(spec=discord.Guild)
    bot_member = MagicMock(spec=discord.Member)
    client_role = MagicMock(spec=discord.Role, id=101, name="Client: Acme")
    context = MagicMock()
    calls: list[str] = []

    async def _ensure(*_args: object, **kwargs: object) -> tuple[None, None, LeadersSyncResult]:
        calls.append("ensure")
        assert kwargs.get("extra_client_role") is client_role
        return None, None, LeadersSyncResult(roles_synced=["Client: Acme"])

    monkeypatch.setattr("bot.hub.leaders.ensure_leaders_channels", _ensure)
    monkeypatch.setattr(
        "bot.networks.roles.resolve_access_role",
        MagicMock(return_value=MagicMock(spec=discord.Role)),
    )
    monkeypatch.setattr(
        "bot.networks.roles.resolve_operator_role_by_name",
        MagicMock(return_value=MagicMock(spec=discord.Role)),
    )
    monkeypatch.setattr(
        "bot.hub.resolve.resolve_human_moderator_role",
        MagicMock(return_value=None),
    )

    result = await grant_leaders_channel_access(
        guild,
        bot_member,
        context,
        client_role,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )
    assert calls == ["ensure"]
    assert result.roles_synced == ["Client: Acme"]
