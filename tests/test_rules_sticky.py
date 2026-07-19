from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.domain.network import Network
from bot.services.guild_channels import (
    join_channel_name,
    resolve_join_requests_channel,
    resolve_network_hub_category,
    resolve_network_join_channel,
)
from bot.services.rules_sticky import (
    RULES_FOOTER,
    RULES_STICKY_SETTINGS_KEY,
    build_rules_embed,
)


def _network(*, join_channel_id: int | None = 501) -> Network:
    return Network(
        id=1,
        key="stingers",
        display_name="Stingers",
        feed_category_id=100,
        output_channel_id=200,
        concat_channel_id=None,
        profile_forum_channel_id=300,
        enabled=True,
        join_channel_id=join_channel_id,
    )


def test_join_channel_name() -> None:
    assert join_channel_name("Stingers") == "join-stingers"


def test_resolve_network_hub_category() -> None:
    guild = MagicMock(spec=discord.Guild)
    match = MagicMock(spec=discord.CategoryChannel)
    match.name = "The Network"
    other = MagicMock(spec=discord.CategoryChannel)
    other.name = "Other"
    guild.categories = [other, match]
    assert resolve_network_hub_category(guild) is match


def test_resolve_network_join_channel_by_id() -> None:
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 501
    guild.get_channel.return_value = channel
    assert resolve_network_join_channel(guild, _network()) is channel


def test_resolve_network_join_channel_by_name() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.get_channel.return_value = None
    hub = MagicMock(spec=discord.CategoryChannel)
    hub.id = 900
    guild.categories = [hub]
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "join-stingers"
    channel.category_id = 900
    guild.text_channels = [channel]
    network = _network(join_channel_id=None)
    assert resolve_network_join_channel(guild, network) is channel


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
