from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from test_guild_init import _patch_init_roles

from bot.domain.client import Client
from bot.domain.errors import NetworkValidationError
from bot.services.guild_init import initialize_guild
from bot.smoke.provision_flow import GuildInitSmokeResult


def _hub_categories(guild: MagicMock) -> dict[str, MagicMock]:
    categories: dict[str, MagicMock] = {}
    for name in ("Moderation", "The Network", "Leaders"):
        cat = MagicMock(spec=discord.CategoryChannel, id=id(name), name=name, channels=[])
        cat.edit = AsyncMock()
        categories[name] = cat
        guild.categories.append(cat)
    return categories


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
        timecode_enabled=False,
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

    wrong_cat = MagicMock(spec=discord.CategoryChannel, id=999, name="Random")
    join_requests = MagicMock(spec=discord.TextChannel)
    join_requests.id = 800
    join_requests.name = "join-requests"
    join_requests.category_id = wrong_cat.id
    join_requests.edit = AsyncMock(return_value=None)
    guild.text_channels = [join_requests]

    def resolve_cat(_guild: MagicMock, name: str) -> MagicMock | None:
        return categories.get(name)

    monkeypatch.setattr("bot.services.guild_init.resolve_category", resolve_cat)
    _patch_init_roles(monkeypatch, access, operator, human_mod)
    monkeypatch.setattr(
        "bot.services.guild_init.run_guild_init_smoke_checks",
        AsyncMock(
            return_value=GuildInitSmokeResult(
                operator_steps=("create category",),
                provision_steps=("create client role",),
            )
        ),
    )
    monkeypatch.setattr(
        "bot.services.guild_init._ensure_human_moderator_role",
        AsyncMock(return_value=human_mod),
    )
    guild.create_text_channel = AsyncMock()
    guild.create_category = AsyncMock()

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is True
    join_requests.edit.assert_awaited()
    edit_kwargs = join_requests.edit.await_args.kwargs
    assert edit_kwargs.get("category") is categories["Moderation"]


@pytest.mark.asyncio
async def test_init_syncs_existing_channel_in_correct_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    categories = _hub_categories(guild)
    moderation = categories["Moderation"]

    commands = MagicMock(spec=discord.TextChannel)
    commands.id = 801
    commands.name = "commands"
    commands.category_id = moderation.id
    commands.edit = AsyncMock()
    guild.text_channels = [commands]

    def resolve_cat(_guild: MagicMock, name: str) -> MagicMock | None:
        return categories.get(name)

    monkeypatch.setattr("bot.services.guild_init.resolve_category", resolve_cat)
    _patch_init_roles(monkeypatch, access, operator, human_mod)
    monkeypatch.setattr(
        "bot.services.guild_init.run_guild_init_smoke_checks",
        AsyncMock(
            return_value=GuildInitSmokeResult(
                operator_steps=("create category",),
                provision_steps=("create client role",),
            )
        ),
    )
    monkeypatch.setattr(
        "bot.services.guild_init._ensure_human_moderator_role",
        AsyncMock(return_value=human_mod),
    )
    guild.create_text_channel = AsyncMock()
    guild.create_category = AsyncMock()

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is True
    commands.edit.assert_awaited()


@pytest.mark.asyncio
async def test_init_with_clients_triggers_reconnect_without_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    categories = _hub_categories(guild)
    client = _stored_client()

    client_role = MagicMock(spec=discord.Role, id=60, name="Client: Acme", position=1)
    client_role.is_default.return_value = False
    guild.roles.append(client_role)

    client_category = MagicMock(spec=discord.CategoryChannel, id=600, name="Acme")
    client_category.edit = AsyncMock()
    guild.categories.append(client_category)
    guild.get_role = MagicMock(return_value=client_role)
    guild.get_channel = MagicMock(
        side_effect=lambda cid: client_category if cid == 600 else None,
    )

    def resolve_cat(_guild: MagicMock, name: str) -> MagicMock | None:
        return categories.get(name)

    monkeypatch.setattr("bot.services.guild_init.resolve_category", resolve_cat)
    _patch_init_roles(monkeypatch, access, operator, human_mod)
    monkeypatch.setattr(
        "bot.services.guild_init.run_guild_init_smoke_checks",
        AsyncMock(
            return_value=GuildInitSmokeResult(
                operator_steps=("create category",),
                provision_steps=("create client role",),
            )
        ),
    )
    monkeypatch.setattr(
        "bot.services.guild_init._ensure_human_moderator_role",
        AsyncMock(return_value=human_mod),
    )
    reconnect = AsyncMock()
    monkeypatch.setattr("bot.services.client_reconnect.reconnect_clients_on_init", reconnect)
    monkeypatch.setattr(
        "bot.services.leaders_channel.ensure_leaders_channels",
        AsyncMock(return_value=(None, None, MagicMock(
            rectification_notes=lambda: [],
            skip_notes=lambda: [],
            failures=[],
        ))),
    )
    guild.create_text_channel = AsyncMock()
    guild.create_category = AsyncMock()

    context = MagicMock()
    context.client_cache.load_cache = AsyncMock()
    context.routing_service.load_cache = AsyncMock()
    context.client_repo.list_all = AsyncMock(return_value=[])
    context.settings_repo.get = AsyncMock(return_value=None)
    context.settings_repo.set = AsyncMock()
    network_bot = MagicMock()

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
        clients=[client],
        bot=network_bot,
        context=context,
        skip_join_smoke=True,
    )

    assert result.success is True
    reconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_fails_when_smoke_probe_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    _patch_init_roles(monkeypatch, access, operator, human_mod)
    monkeypatch.setattr(
        "bot.services.guild_init.run_guild_init_smoke_checks",
        AsyncMock(
            side_effect=NetworkValidationError("Join-approval provisioning probe failed"),
        ),
    )

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is False
    assert "provisioning probe" in (result.reason or "").casefold()


@pytest.mark.asyncio
async def test_init_survives_unexpected_exception_with_typed_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    _patch_init_roles(monkeypatch, access, operator, human_mod)
    monkeypatch.setattr(
        "bot.services.guild_init.run_guild_init_smoke_checks",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is False
    assert "RuntimeError" in (result.reason or "")
