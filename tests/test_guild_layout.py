from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.services.guild_layout import (
    CATEGORY_NETWORK,
    CHANNEL_JOIN_REQUESTS,
    CHANNEL_WELCOME_SINK,
    join_channel_name,
    resolve_human_moderator_role,
    resolve_moderator_role,
    resolve_network_announcement_channel,
    resolve_network_hub_category,
    resolve_welcome_sink_channel,
)


def test_join_channel_name() -> None:
    assert join_channel_name("Stingers") == "join-stingers"


def test_resolve_network_hub_category() -> None:
    guild = MagicMock(spec=discord.Guild)
    match = MagicMock(spec=discord.CategoryChannel)
    match.name = CATEGORY_NETWORK
    guild.categories = [match]
    assert resolve_network_hub_category(guild) is match


def test_resolve_human_moderator_role_prefers_moderator() -> None:
    guild = MagicMock(spec=discord.Guild)
    bot_staff = MagicMock(spec=discord.Role)
    bot_staff.name = "The Network Moderator"
    human = MagicMock(spec=discord.Role)
    human.name = "Moderator"
    guild.roles = [bot_staff, human]
    assert resolve_human_moderator_role(guild) is human


def test_resolve_moderator_role_prefers_network_moderator() -> None:
    guild = MagicMock(spec=discord.Guild)
    legacy = MagicMock(spec=discord.Role)
    legacy.name = "Moderator"
    preferred = MagicMock(spec=discord.Role)
    preferred.name = "The Network Moderator"
    guild.roles = [legacy, preferred]
    assert resolve_moderator_role(guild) is preferred


def test_resolve_moderator_role_falls_back_to_legacy() -> None:
    guild = MagicMock(spec=discord.Guild)
    role = MagicMock(spec=discord.Role)
    role.name = "Moderator"
    guild.roles = [role]
    assert resolve_moderator_role(guild) is role


def test_join_requests_channel_name_constant() -> None:
    assert CHANNEL_JOIN_REQUESTS == "join-requests"


def test_resolve_welcome_sink_channel() -> None:
    guild = MagicMock(spec=discord.Guild)
    sink = MagicMock(spec=discord.TextChannel)
    sink.name = CHANNEL_WELCOME_SINK
    other = MagicMock(spec=discord.TextChannel)
    other.name = "rules"
    guild.text_channels = [other, sink]
    assert resolve_welcome_sink_channel(guild) is sink


def test_resolve_network_announcement_channel() -> None:
    guild = MagicMock(spec=discord.Guild)
    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    match = MagicMock()
    match.name = "stingers-announcements"
    match.category_id = 10
    match.type = discord.ChannelType.news
    other = MagicMock()
    other.name = "other-announcements"
    other.category_id = 11
    other.type = discord.ChannelType.news
    guild.channels = [other, match]
    assert resolve_network_announcement_channel(guild, "stingers", category=category) is match
