from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.channels.order import (
    align_categories_hub_first,
    align_positions,
    next_trailing_position,
)


@pytest.mark.asyncio
async def test_align_positions_skips_correct_and_edits_wrong() -> None:
    first = MagicMock(spec=discord.TextChannel, id=1, name="a", position=0)
    first.edit = AsyncMock()
    second = MagicMock(spec=discord.TextChannel, id=2, name="b", position=5)
    second.edit = AsyncMock()

    failures = await align_positions(
        [first, second],
        reason="test order",
    )

    assert failures == []
    first.edit.assert_not_awaited()
    second.edit.assert_awaited_once_with(position=1, reason="test order")


@pytest.mark.asyncio
async def test_align_categories_hub_first_packs_clients_below() -> None:
    hub = MagicMock(spec=discord.CategoryChannel, id=10, name="Moderation", position=2)
    hub.edit = AsyncMock()
    client = MagicMock(spec=discord.CategoryChannel, id=20, name="Acme", position=0)
    client.edit = AsyncMock()
    guild = MagicMock(spec=discord.Guild)
    guild.categories = [client, hub]

    failures = await align_categories_hub_first(
        guild,
        [hub],
        reason="hub first",
    )

    assert failures == []
    hub.edit.assert_awaited_once_with(position=0, reason="hub first")
    client.edit.assert_awaited_once_with(position=1, reason="hub first")


def test_next_trailing_position() -> None:
    assert next_trailing_position(leading_count=3, trailing_count=0) == 3
    assert next_trailing_position(leading_count=3, trailing_count=2) == 5
