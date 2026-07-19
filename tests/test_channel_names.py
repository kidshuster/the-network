from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.services.channel_names import announcement_channel_base_name, build_network_channel_name


def test_announcement_channel_base_name() -> None:
    assert announcement_channel_base_name("Stingers") == "stingers-announcements"


def test_build_network_channel_name_uses_suffix() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.channels = []
    name = build_network_channel_name(guild, "stingers", "announcements")
    assert name == "stingers-announcements"
