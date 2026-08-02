from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.guild_init import _reorder_hub_categories, GuildInitResult


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
        patch.setattr("bot.services.guild_init._run_init_step", run_step)
        await _reorder_hub_categories(moderation, network, result=result)

    moderation.edit.assert_awaited_once_with(
        position=0,
        reason="The Network server init",
    )
    network.edit.assert_awaited_once_with(
        position=1,
        reason="The Network server init",
    )
