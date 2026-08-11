from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.features.recipes.hub.initialize import (
    GuildInitResult,
    _reorder_guild_categories,
    _reorder_hub_categories,
)


@pytest.mark.asyncio
async def test_reorder_hub_categories_places_moderation_and_network_at_top() -> None:
    moderation = MagicMock(spec=discord.CategoryChannel)
    moderation.name = "Moderation"
    moderation.edit = AsyncMock()
    network = MagicMock(spec=discord.CategoryChannel)
    network.name = "The Network"
    network.edit = AsyncMock()
    result = GuildInitResult(success=True)

    async def run_step(_result, _step, action):
        return await action()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("bot.features.hub.reconcilers._run_init_step", run_step)
        await _reorder_hub_categories(moderation, network, result=result)

    moderation.edit.assert_awaited_once_with(
        position=0,
        reason="The Network server init",
    )
    network.edit.assert_awaited_once_with(
        position=1,
        reason="The Network server init",
    )


@pytest.mark.asyncio
async def test_reorder_guild_categories_places_leaders_below_network_and_clients_after() -> None:
    moderation = MagicMock(spec=discord.CategoryChannel)
    moderation.name = "Moderation"
    moderation.edit = AsyncMock()
    network = MagicMock(spec=discord.CategoryChannel)
    network.name = "The Network"
    network.edit = AsyncMock()
    leaders = MagicMock(spec=discord.CategoryChannel)
    leaders.name = "Leaders"
    leaders.edit = AsyncMock()
    client_a = MagicMock(spec=discord.CategoryChannel)
    client_a.name = "Alpha Server"
    client_a.edit = AsyncMock()
    client_b = MagicMock(spec=discord.CategoryChannel)
    client_b.name = "Beta Server"
    client_b.edit = AsyncMock()
    result = GuildInitResult(success=True)

    async def run_step(_result, _step, action):
        return await action()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("bot.features.hub.reconcilers._run_init_step", run_step)
        await _reorder_guild_categories(
            moderation,
            network,
            leaders_category=leaders,
            client_categories=[client_a, client_b],
            result=result,
        )

    moderation.edit.assert_awaited_once_with(position=0, reason="The Network server init")
    network.edit.assert_awaited_once_with(position=1, reason="The Network server init")
    leaders.edit.assert_awaited_once_with(position=2, reason="The Network server init")
    client_a.edit.assert_awaited_once_with(position=3, reason="The Network server init")
    client_b.edit.assert_awaited_once_with(position=4, reason="The Network server init")
