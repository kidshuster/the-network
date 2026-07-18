from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.services.channel_names import build_network_channel_name, build_unique_channel_name
from bot.services.profile_provision import (
    build_partner_role_name,
    build_unique_role_name,
    slugify_server_name,
)


def test_slugify_server_name() -> None:
    assert slugify_server_name("Test Server 1") == "test-server-1"
    assert slugify_server_name("!!!") == "partner"


def test_build_partner_role_name() -> None:
    assert build_partner_role_name("Acme Corp") == "Partner: Acme Corp"


def test_build_unique_role_name() -> None:
    guild = MagicMock(spec=discord.Guild)
    existing = MagicMock(spec=discord.Role)
    existing.name = "Partner: Acme"
    guild.roles = [existing]
    assert build_unique_role_name(guild, "Partner: Acme") == "Partner: Acme-2"


def test_build_unique_channel_name() -> None:
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "acme-feed"
    guild.channels = [channel]
    assert build_unique_channel_name(guild, "acme-feed") == "acme-feed-2"


def test_build_network_channel_name() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.channels = []
    assert build_network_channel_name(guild, "stingers", "profiles") == "stingers-profiles"
    assert build_network_channel_name(guild, "Stingers", "test1-feed") == "stingers-test1-feed"
