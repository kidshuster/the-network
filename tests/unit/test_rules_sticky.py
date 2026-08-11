from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.features.channels.resolve import (
    resolve_join_requests_channel,
    resolve_network_hub_category,
)
from bot.features.channels.stickies.rules import (
    RULES_FOOTER,
    RULES_STICKY_SETTINGS_KEY,
    build_rules_embed,
)


def test_resolve_network_hub_category() -> None:
    guild = MagicMock(spec=discord.Guild)
    match = MagicMock(spec=discord.CategoryChannel)
    match.name = "The Network"
    other = MagicMock(spec=discord.CategoryChannel)
    other.name = "Other"
    guild.categories = [other, match]
    assert resolve_network_hub_category(guild) is match


def test_resolve_join_requests_channel() -> None:
    guild = MagicMock(spec=discord.Guild)
    match = MagicMock(spec=discord.TextChannel)
    match.name = "join-requests"
    other = MagicMock(spec=discord.TextChannel)
    other.name = "general"
    guild.text_channels = [other, match]
    assert resolve_join_requests_channel(guild) is match


def test_build_rules_embed_covers_guidelines() -> None:
    embed = build_rules_embed()
    assert embed.title is not None
    assert "Relay Rules" in embed.title
    assert len(embed.fields) >= 4
    assert embed.footer is not None
    assert embed.footer.text == RULES_FOOTER


def test_rules_sticky_settings_key() -> None:
    assert RULES_STICKY_SETTINGS_KEY == "hub_rules_sticky_message"
