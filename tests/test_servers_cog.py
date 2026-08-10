from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.cogs.servers import ServerCog
from bot.messages import render_text


@pytest.mark.asyncio
async def test_init_server_rejects_non_central_guild() -> None:
    bot = MagicMock()
    bot.settings.guild_id = 100
    cog = ServerCog(bot)

    interaction = MagicMock()
    interaction.guild = MagicMock(id=999)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    await cog.init_server.callback(cog, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    interaction.followup.send.assert_awaited_once_with(
        render_text("central_guild_only"),
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_uninit_server_rejects_missing_bot_member() -> None:
    bot = MagicMock()
    bot.settings.guild_id = 100
    cog = ServerCog(bot)

    guild = MagicMock(id=100)
    guild.me = None
    interaction = MagicMock()
    interaction.guild = guild
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    await cog.uninit_server.callback(cog, interaction)

    interaction.followup.send.assert_awaited_once_with(
        render_text("bot_member_unavailable"),
        ephemeral=True,
    )
