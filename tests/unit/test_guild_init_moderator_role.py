from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.features.recipes.hub.initialize import GuildInitResult, _ensure_human_moderator_role


@pytest.mark.asyncio
async def test_ensure_human_moderator_role_creates_mentionable_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    bot = MagicMock(spec=discord.Member)
    bot.top_role = MagicMock(position=10)

    created_role = MagicMock(spec=discord.Role)
    guild.create_role = AsyncMock(return_value=created_role)
    monkeypatch.setattr(
        "bot.features.hub.reconcilers.resolve_human_moderator_role",
        MagicMock(return_value=None),
    )

    result = GuildInitResult(success=True)
    role = await _ensure_human_moderator_role(guild, bot, result=result)

    assert role is created_role
    guild.create_role.assert_awaited_once()
    kwargs = guild.create_role.await_args.kwargs
    assert kwargs["name"] == "Moderator"
    assert kwargs["mentionable"] is True


@pytest.mark.asyncio
async def test_ensure_human_moderator_role_enables_mentions_on_existing_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    bot = MagicMock(spec=discord.Member)
    bot.top_role = MagicMock(position=10)

    role = MagicMock(spec=discord.Role)
    role.name = "Moderator"
    role.position = 5
    role.permissions = discord.Permissions.none()
    role.mentionable = False
    role.edit = AsyncMock(return_value=role)

    monkeypatch.setattr(
        "bot.features.hub.reconcilers.resolve_human_moderator_role",
        MagicMock(return_value=role),
    )

    result = GuildInitResult(success=True)
    updated = await _ensure_human_moderator_role(guild, bot, result=result)

    assert updated is role
    role.edit.assert_awaited_once()
    assert role.edit.await_args.kwargs["mentionable"] is True
