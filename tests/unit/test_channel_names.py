from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.core.clients.names import build_network_channel_name


def test_build_network_channel_name_uses_suffix() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.channels = []
    name = build_network_channel_name(guild, "stingers", "announcements")
    assert name == "stingers-announcements"
