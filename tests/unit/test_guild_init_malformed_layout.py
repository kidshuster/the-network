from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from test_guild_init import _patch_init_roles
from view_registry_helpers import make_test_view_registry

from bot.core.models.client import Client
from bot.features.recipes.hub.initialize import initialize_guild


def _full_channel_permissions() -> discord.Permissions:
    return discord.Permissions(
        view_channel=True,
        manage_channels=True,
        manage_roles=True,
    )


def _hub_categories(guild: MagicMock) -> dict[str, MagicMock]:
    categories: dict[str, MagicMock] = {}
    for name in ("Moderation", "The Network", "Leaders"):
        cat = MagicMock(spec=discord.CategoryChannel)
        cat.id = id(name)
        cat.name = name
        cat.channels = []
        cat.overwrites = {}
        cat.edit = AsyncMock()
        cat.permissions_for = MagicMock(return_value=_full_channel_permissions())
        categories[name] = cat
        guild.categories.append(cat)
    return categories


def _mock_created_category(**kwargs: object) -> MagicMock:
    cat = MagicMock(spec=discord.CategoryChannel)
    cat.id = id(kwargs.get("name", "category"))
    cat.name = str(kwargs.get("name", "category"))
    cat.channels = []
    cat.overwrites = dict(kwargs.get("overwrites") or {})  # type: ignore[arg-type]
    cat.edit = AsyncMock()
    cat.set_permissions = AsyncMock()
    cat.permissions_for = MagicMock(return_value=_full_channel_permissions())
    return cat


def _mock_created_text_channel(**kwargs: object) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = id(kwargs.get("name", "channel"))
    channel.name = str(kwargs.get("name", "channel"))
    channel.mention = f"#{channel.name}"
    channel.category_id = getattr(kwargs.get("category"), "id", None)
    channel.overwrites = dict(kwargs.get("overwrites") or {})  # type: ignore[arg-type]
    channel.edit = AsyncMock()
    channel.set_permissions = AsyncMock()
    channel.permissions_for = MagicMock(return_value=_full_channel_permissions())
    return channel


def _stored_client() -> Client:
    return Client(
        id=1,
        guild_id=100,
        server_name="Acme",
        display_name="Acme",
        category_id=600,
        client_role_id=60,
        profile_channel_id=700,
        profile_message_id=701,
        enabled=True,
        timecode_enabled=False, read_only=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


@pytest.mark.asyncio
async def test_init_moves_channel_from_wrong_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    categories = _hub_categories(guild)

    wrong_cat = MagicMock(spec=discord.CategoryChannel)
    wrong_cat.id = 999
    wrong_cat.name = "Random"
    join_requests = MagicMock(spec=discord.TextChannel)
    join_requests.id = 800
    join_requests.name = "join-requests"
    join_requests.category_id = wrong_cat.id
    join_requests.overwrites = {}
    join_requests.edit = AsyncMock(return_value=None)
    join_requests.permissions_for = MagicMock(return_value=_full_channel_permissions())
    guild.text_channels = [join_requests]
    guild.create_text_channel = AsyncMock(side_effect=_mock_created_text_channel)

    _patch_init_roles(monkeypatch, access, operator, human_mod)
    monkeypatch.setattr(
        "bot.features.recipes.hub.reconcilers._ensure_human_moderator_role",
        AsyncMock(return_value=human_mod),
    )
    guild.create_category = AsyncMock(side_effect=_mock_created_category)

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is True
    join_requests.edit.assert_awaited()
    category_edits = [call.kwargs.get("category") for call in join_requests.edit.await_args_list]
    assert categories["Moderation"] in category_edits


@pytest.mark.asyncio
async def test_init_removes_retired_commands_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    categories = _hub_categories(guild)
    moderation = categories["Moderation"]

    commands = MagicMock(spec=discord.TextChannel)
    commands.id = 801
    commands.name = "commands"
    commands.category_id = moderation.id
    commands.overwrites = {}
    commands.edit = AsyncMock()
    commands.delete = AsyncMock()
    commands.permissions_for = MagicMock(return_value=_full_channel_permissions())
    guild.text_channels = [commands]
    guild.get_channel.side_effect = lambda channel_id: commands if channel_id == 801 else None
    guild.create_text_channel = AsyncMock(side_effect=_mock_created_text_channel)
    guild.create_category = AsyncMock(side_effect=_mock_created_category)

    _patch_init_roles(monkeypatch, access, operator, human_mod)
    monkeypatch.setattr(
        "bot.features.recipes.hub.reconcilers._ensure_human_moderator_role",
        AsyncMock(return_value=human_mod),
    )

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is True
    commands.delete.assert_awaited()


@pytest.mark.asyncio
async def test_init_with_clients_triggers_reconnect_without_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    _hub_categories(guild)
    client = _stored_client()

    client_role = MagicMock(spec=discord.Role, id=60, name="Client: Acme", position=1)
    client_role.is_default.return_value = False
    guild.roles.append(client_role)

    client_category = MagicMock(spec=discord.CategoryChannel, id=600, name="Acme")
    client_category.edit = AsyncMock()
    client_category.overwrites = {}
    client_category.permissions_for = MagicMock(return_value=_full_channel_permissions())
    guild.categories.append(client_category)
    guild.get_role = MagicMock(return_value=client_role)
    guild.get_channel = MagicMock(
        side_effect=lambda cid: client_category if cid == 600 else None,
    )

    _patch_init_roles(monkeypatch, access, operator, human_mod)
    monkeypatch.setattr(
        "bot.features.recipes.hub.reconcilers._ensure_human_moderator_role",
        AsyncMock(return_value=human_mod),
    )
    reconnect = AsyncMock()
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.reconnect.reconnect_clients_on_init",
        reconnect,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.leaders.ensure_leaders_channels",
        AsyncMock(
            return_value=(
                None,
                None,
                MagicMock(
                    rectification_notes=lambda: [],
                    skip_notes=lambda: [],
                    failures=[],
                ),
            )
        ),
    )
    guild.create_text_channel = AsyncMock(side_effect=_mock_created_text_channel)
    guild.create_category = AsyncMock(side_effect=_mock_created_category)

    context = MagicMock()
    context.client_cache.load_cache = AsyncMock()
    context.routing_service.load_cache = AsyncMock()
    context.refresh_projections = AsyncMock()
    context.store.clients.list_all = AsyncMock(return_value=[])
    context.store.settings.get = AsyncMock(return_value=None)
    context.store.settings.set = AsyncMock()
    network_bot = MagicMock()

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
        clients=[client],
        bot=network_bot,
        context=context,
        view_registry=make_test_view_registry(),
    )

    assert result.success is True
    reconnect.assert_awaited_once()
