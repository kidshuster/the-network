from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.channels.resolve import HUB_CATEGORY_LEADERS, HUB_CHANNEL_CHANGELOG, HUB_CHANNEL_LEADERS
from tests.core.server_init_probes import (
    _collect_leaders_access_gaps,
    _role_can_view_channel,
)


def test_role_can_view_channel_respects_explicit_deny() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    role = MagicMock(spec=discord.Role)
    channel.overwrites_for.return_value = discord.PermissionOverwrite(view_channel=False)
    channel.permissions_for.return_value = discord.Permissions(view_channel=False)
    assert _role_can_view_channel(channel, role) is False


def test_role_can_view_channel_allows_explicit_allow() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    role = MagicMock(spec=discord.Role)
    channel.overwrites_for.return_value = discord.PermissionOverwrite(view_channel=True)
    channel.permissions_for.return_value = discord.Permissions(view_channel=True)
    assert _role_can_view_channel(channel, role) is True


def _client_context(*, roles: list[MagicMock]) -> MagicMock:
    context = MagicMock()
    clients = []
    for index, role in enumerate(roles):
        client = MagicMock(
            guild_id=100,
            client_role_id=role.id,
            server_name=f"Client{index}",
        )
        clients.append(client)
    context.store.clients.list_all = AsyncMock(return_value=clients)
    return context


def _patch_leaders_layout(
    monkeypatch: pytest.MonkeyPatch,
    *,
    category: MagicMock,
    leaders: MagicMock | None,
    changelog: MagicMock | None,
) -> None:
    def fake_resolve_hub_category(_guild: object, category_id: str) -> MagicMock | None:
        if category_id == HUB_CATEGORY_LEADERS:
            return category
        return None

    def fake_resolve_hub_channel(
        _guild: object,
        channel_id: str,
        *,
        category_id: int | None = None,
        include_announcement: bool = True,
    ) -> MagicMock | None:
        del category_id, include_announcement
        if channel_id == HUB_CHANNEL_LEADERS:
            return leaders
        if channel_id == HUB_CHANNEL_CHANGELOG:
            return changelog
        return None

    monkeypatch.setattr(
        "tests.core.server_init_probes.resolve_hub_category",
        fake_resolve_hub_category,
    )
    monkeypatch.setattr(
        "tests.core.server_init_probes.resolve_hub_channel",
        fake_resolve_hub_channel,
    )


@pytest.mark.asyncio
async def test_collect_leaders_access_gaps_when_all_clients_can_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild, id=100)
    role_a = MagicMock(spec=discord.Role, id=1, name="Client: A")
    role_b = MagicMock(spec=discord.Role, id=2, name="Client: B")
    guild.get_role = MagicMock(side_effect=lambda rid: {1: role_a, 2: role_b}[rid])

    category = MagicMock(spec=discord.CategoryChannel, mention="Leaders")
    leaders = MagicMock(spec=discord.TextChannel, mention="#leaders-channel")
    changelog = MagicMock(spec=discord.TextChannel, mention="#changelog")
    for channel in (category, leaders, changelog):
        channel.overwrites_for.return_value = discord.PermissionOverwrite()
        channel.permissions_for.return_value = discord.Permissions(view_channel=True)

    _patch_leaders_layout(
        monkeypatch,
        category=category,
        leaders=leaders,
        changelog=changelog,
    )

    gaps = await _collect_leaders_access_gaps(guild, _client_context(roles=[role_a, role_b]))
    assert gaps == []


@pytest.mark.asyncio
async def test_collect_leaders_access_gaps_reports_missing_leaders_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild, id=100)
    role = MagicMock(spec=discord.Role, id=1, name="Client: Acme")
    guild.get_role = MagicMock(return_value=role)

    category = MagicMock(spec=discord.CategoryChannel, mention="Leaders")
    category.overwrites_for.return_value = discord.PermissionOverwrite()
    category.permissions_for.return_value = discord.Permissions(view_channel=True)

    leaders = MagicMock(spec=discord.TextChannel, mention="#leaders-channel")
    leaders.overwrites_for.return_value = discord.PermissionOverwrite(view_channel=False)
    leaders.permissions_for.return_value = discord.Permissions(view_channel=False)

    _patch_leaders_layout(
        monkeypatch,
        category=category,
        leaders=leaders,
        changelog=None,
    )

    gaps = await _collect_leaders_access_gaps(guild, _client_context(roles=[role]))
    assert any("missing view on leaders-channel" in gap for gap in gaps)
    assert any("changelog not found" in gap for gap in gaps)


@pytest.mark.asyncio
async def test_collect_leaders_access_gaps_when_no_clients() -> None:
    guild = MagicMock(spec=discord.Guild, id=100)
    context = MagicMock()
    context.store.clients.list_all = AsyncMock(return_value=[])
    gaps = await _collect_leaders_access_gaps(guild, context)
    assert gaps == []
