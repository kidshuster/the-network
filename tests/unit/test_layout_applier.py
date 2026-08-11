from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import http_50013, make_guild_with_roles

from bot.app.layout import LayoutContext, compile_hub
from bot.app.layout.applier import _ensure_channel
from bot.constants import DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME


def _hub_context() -> LayoutContext:
    guild, bot, moderator, access, operator = make_guild_with_roles()
    bot_access = discord.utils.get(guild.roles, name=DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME)
    assert bot_access is not None
    return LayoutContext(
        guild=guild,
        bot_member=bot,
        access_role=access,
        moderator_role=moderator,
        operator_role=operator,
        bot_access_role=bot_access,
        reason="test layout apply",
    )


def _http_exc(message: str, *, code: int, status: int = 403) -> discord.HTTPException:
    exc = discord.HTTPException(MagicMock(), message)
    exc.status = status
    exc.code = code
    return exc


@pytest.mark.asyncio
async def test_community_channel_placement_50013_still_reconciles_permissions() -> None:
    context = _hub_context()
    guild = context.guild

    network = MagicMock(spec=discord.CategoryChannel)
    network.id = 501
    network.name = "The Network"
    network.overwrites = {}
    network.edit = AsyncMock()

    rules = MagicMock(spec=discord.TextChannel)
    rules.id = 777
    rules.name = "rules"
    rules.topic = None
    rules.category_id = None
    rules.overwrites = {}
    rules.edit = AsyncMock(side_effect=http_50013())
    rules.set_permissions = AsyncMock()
    rules.is_news = MagicMock(return_value=False)

    guild.categories = [network]
    guild.text_channels = [rules]
    guild.rules_channel = rules
    guild.public_updates_channel = None

    rules_resource = next(item for item in compile_hub(context) if item.id == "rules")
    result = await _ensure_channel(
        context,
        rules_resource,
        {"network": network},
        reconcile_only=False,
    )

    assert result.channel is rules
    assert result.detail is not None
    assert result.detail.startswith("placement:")
    assert any(call.kwargs.get("overwrites") for call in rules.edit.await_args_list) or (
        rules.set_permissions.await_count >= 1
    )


@pytest.mark.asyncio
async def test_inaccessible_hub_channel_is_recreated() -> None:
    context = _hub_context()
    guild = context.guild

    moderation = MagicMock(spec=discord.CategoryChannel)
    moderation.id = 500
    moderation.name = "Moderation"
    moderation.overwrites = {}
    moderation.edit = AsyncMock()

    locked = MagicMock(spec=discord.TextChannel)
    locked.id = 801
    locked.name = "join-requests"
    locked.topic = "Pending client join requests"
    locked.category_id = moderation.id
    locked.overwrites = {}
    locked.is_news = MagicMock(return_value=False)
    missing = _http_exc("Missing Access", code=50001)
    locked.edit = AsyncMock(side_effect=missing)
    locked.set_permissions = AsyncMock(side_effect=missing)

    async def _delete(*, reason: str | None = None) -> None:
        _ = reason
        guild.text_channels = [
            channel for channel in guild.text_channels if channel.id != locked.id
        ]

    locked.delete = AsyncMock(side_effect=_delete)

    recreated = MagicMock(spec=discord.TextChannel)
    recreated.id = 802
    recreated.name = "join-requests"
    recreated.overwrites = {}
    recreated.edit = AsyncMock()
    recreated.set_permissions = AsyncMock()
    recreated.category_id = moderation.id

    guild.categories = [moderation]
    guild.text_channels = [locked]
    guild.rules_channel = None
    guild.public_updates_channel = None
    guild.create_text_channel = AsyncMock(return_value=recreated)

    resource = next(item for item in compile_hub(context) if item.id == "join_requests")
    result = await _ensure_channel(
        context,
        resource,
        {"moderation": moderation},
        reconcile_only=False,
    )

    locked.delete.assert_awaited()
    guild.create_text_channel.assert_awaited()
    assert "overwrites" not in guild.create_text_channel.await_args.kwargs
    assert result.channel is recreated
    assert result.success is True


@pytest.mark.asyncio
async def test_community_channel_renames_even_when_category_move_fails() -> None:
    context = _hub_context()
    guild = context.guild

    network = MagicMock(spec=discord.CategoryChannel)
    network.id = 501
    network.name = "The Network"
    network.overwrites = {}
    network.edit = AsyncMock()

    rules = MagicMock(spec=discord.TextChannel)
    rules.id = 777
    rules.name = "community-rules"
    rules.topic = None
    rules.category_id = None
    rules.overwrites = {}
    rules.set_permissions = AsyncMock()
    rules.is_news = MagicMock(return_value=False)

    async def _edit(**kwargs: object) -> None:
        if "category" in kwargs:
            raise http_50013()
        if "name" in kwargs:
            rules.name = str(kwargs["name"])

    rules.edit = AsyncMock(side_effect=_edit)

    guild.categories = [network]
    guild.text_channels = [rules]
    guild.rules_channel = rules
    guild.public_updates_channel = None

    rules_resource = next(item for item in compile_hub(context) if item.id == "rules")
    result = await _ensure_channel(
        context,
        rules_resource,
        {"network": network},
        reconcile_only=False,
    )

    assert rules.name == "rules"
    rename_calls = [
        call for call in rules.edit.await_args_list if call.kwargs.get("name") == "rules"
    ]
    assert rename_calls
    assert result.detail is not None
    assert result.detail.startswith("placement:")
    assert rules.set_permissions.await_count >= 1 or any(
        call.kwargs.get("overwrites") for call in rules.edit.await_args_list
    )
