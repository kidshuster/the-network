from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.services.guild_permissions import build_server_feed_channel_overwrites
from bot.services.profile_provision import (
    build_server_role_name,
    build_unique_role_name,
    slugify_server_name,
)


def test_slugify_server_name() -> None:
    assert slugify_server_name("Test Server 1") == "test-server-1"
    assert slugify_server_name("!!!") == "server"


def test_build_server_role_name() -> None:
    assert build_server_role_name("Acme Corp") == "Partner: Acme Corp"


def test_build_unique_role_name() -> None:
    guild = MagicMock(spec=discord.Guild)
    existing = MagicMock(spec=discord.Role)
    existing.name = "Partner: Acme"
    guild.roles = [existing]
    assert build_unique_role_name(guild, "Partner: Acme") == "Partner: Acme-2"


def test_server_feed_channel_overwrites() -> None:
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    guild.default_role = everyone
    partner = MagicMock(spec=discord.Role)
    admin = MagicMock(spec=discord.Role)
    moderator = MagicMock(spec=discord.Role)
    moderator.position = 2
    bot = MagicMock(spec=discord.Member)
    bot.top_role = MagicMock(spec=discord.Role, position=5)
    partner.position = 1
    admin.position = 1

    overwrites = dict(
        build_server_feed_channel_overwrites(
            guild,
            bot,
            partner,
            admin,
            moderator,
        )
    )

    assert overwrites[everyone].view_channel is False
    assert overwrites[partner].view_channel is True
    assert overwrites[partner].manage_webhooks is True
    assert overwrites[partner].send_messages is False
    assert overwrites[partner].use_application_commands is False
    assert overwrites[bot].manage_messages is True
