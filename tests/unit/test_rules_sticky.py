from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.channels.layout.managed import hub_category_name, hub_channel_name
from bot.channels.resolve import (
    HUB_CATEGORY_NETWORK,
    HUB_CHANNEL_JOIN_REQUESTS,
    join_channel_name,
    resolve_hub_category,
    resolve_hub_channel,
    resolve_network_join_channel,
)
from bot.channels.stickies.rules import (
    RULES_FOOTER,
    RULES_STICKY_SETTINGS_KEY,
    build_rules_embed,
)
from bot.core.models.network import Network


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


def test_resolve_hub_category_network() -> None:
    guild = MagicMock(spec=discord.Guild)
    match = MagicMock(spec=discord.CategoryChannel)
    match.name = hub_category_name(HUB_CATEGORY_NETWORK)
    other = MagicMock(spec=discord.CategoryChannel)
    other.name = "Other"
    guild.categories = [other, match]
    assert resolve_hub_category(guild, HUB_CATEGORY_NETWORK) is match


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
    hub.name = hub_category_name(HUB_CATEGORY_NETWORK)
    guild.categories = [hub]
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "join-stingers"
    channel.category_id = 900
    guild.text_channels = [channel]
    network = _network(join_channel_id=None)
    assert resolve_network_join_channel(guild, network) is channel


def test_resolve_hub_channel_join_requests() -> None:
    guild = MagicMock(spec=discord.Guild)
    match = MagicMock(spec=discord.TextChannel)
    match.name = hub_channel_name(HUB_CHANNEL_JOIN_REQUESTS)
    match.is_news = MagicMock(return_value=False)
    other = MagicMock(spec=discord.TextChannel)
    other.name = "general"
    other.is_news = MagicMock(return_value=False)
    guild.text_channels = [other, match]
    assert resolve_hub_channel(guild, HUB_CHANNEL_JOIN_REQUESTS) is match


def test_build_rules_embed_covers_guidelines() -> None:
    embed = build_rules_embed()
    assert embed.title is not None
    assert "Relay Rules" in embed.title
    assert len(embed.fields) >= 4
    assert embed.footer is not None
    assert embed.footer.text == RULES_FOOTER


def test_rules_sticky_settings_key() -> None:
    assert RULES_STICKY_SETTINGS_KEY == "hub_rules_sticky_message"
