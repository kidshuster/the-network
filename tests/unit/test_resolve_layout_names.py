from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from bot.app.layout.loader import clear_layout_cache
from bot.app.layout.managed import (
    hub_category_name,
    hub_channel_aliases,
    hub_channel_name,
)
from bot.features.channels.resolve import (
    HUB_CATEGORY_MODERATION,
    HUB_CATEGORY_NETWORK,
    HUB_CHANNEL_ADMIN,
    HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
    resolve_hub_category,
    resolve_hub_channel,
)


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    clear_layout_cache()
    yield
    clear_layout_cache()


def test_hub_channel_aliases_include_current_and_legacy_names() -> None:
    aliases = hub_channel_aliases(HUB_CHANNEL_ADMIN)
    assert hub_channel_name(HUB_CHANNEL_ADMIN) == aliases[0]
    assert aliases[0] == "admin"
    assert "commands" in aliases
    assert "moderator-only" in aliases


def test_resolve_hub_category_matches_yaml_name() -> None:
    guild = MagicMock(spec=discord.Guild)
    match = MagicMock(spec=discord.CategoryChannel)
    match.name = hub_category_name(HUB_CATEGORY_NETWORK)
    guild.categories = [match]

    assert resolve_hub_category(guild, HUB_CATEGORY_NETWORK) is match


def test_resolve_hub_channel_matches_legacy_name() -> None:
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "mod-only"
    channel.category_id = 10
    channel.is_news = MagicMock(return_value=False)
    guild.text_channels = [channel]

    found = resolve_hub_channel(guild, HUB_CHANNEL_ADMIN)
    assert found is channel

    found_in_category = resolve_hub_channel(
        guild,
        HUB_CHANNEL_ADMIN,
        category_id=10,
    )
    assert found_in_category is channel
    assert (
        resolve_hub_channel(
            guild,
            HUB_CHANNEL_ADMIN,
            category_id=99,
        )
        is None
    )


def test_resolve_hub_channel_respects_category_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "bot.features.channels.resolve.hub_channel_aliases",
        lambda channel_id: ("ops",) if channel_id == HUB_CHANNEL_ADMIN else (),
    )
    guild = MagicMock(spec=discord.Guild)
    moderation = MagicMock(spec=discord.CategoryChannel)
    moderation.id = 5
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "ops"
    channel.category_id = 5
    channel.is_news = MagicMock(return_value=False)
    guild.text_channels = [channel]

    assert (
        resolve_hub_channel(
            guild,
            HUB_CHANNEL_ADMIN,
            category_id=moderation.id,
        )
        is channel
    )
    assert (
        resolve_hub_channel(
            guild,
            HUB_CHANNEL_ADMIN,
            category_id=99,
        )
        is None
    )


def test_resolve_hub_channel_skips_news_when_include_announcement_false() -> None:
    guild = MagicMock(spec=discord.Guild)
    mod_category = MagicMock(spec=discord.CategoryChannel)
    mod_category.id = 10

    plain = MagicMock(spec=discord.TextChannel)
    plain.name = hub_channel_name(HUB_CHANNEL_NETWORK_ANNOUNCEMENTS)
    plain.category_id = mod_category.id
    plain.is_news = MagicMock(return_value=False)

    announcement = MagicMock(spec=discord.TextChannel)
    announcement.name = hub_channel_name(HUB_CHANNEL_NETWORK_ANNOUNCEMENTS)
    announcement.category_id = mod_category.id
    announcement.is_news = MagicMock(return_value=True)

    guild.text_channels = [plain, announcement]
    assert (
        resolve_hub_channel(
            guild,
            HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
            category_id=mod_category.id,
            include_announcement=False,
        )
        is plain
    )

    guild.text_channels = [announcement]
    assert (
        resolve_hub_channel(
            guild,
            HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
            category_id=mod_category.id,
            include_announcement=False,
        )
        is None
    )


def test_resolve_hub_category_uses_moderation_yaml_name() -> None:
    guild = MagicMock(spec=discord.Guild)
    match = MagicMock(spec=discord.CategoryChannel)
    match.name = hub_category_name(HUB_CATEGORY_MODERATION)
    guild.categories = [match]

    assert resolve_hub_category(guild, HUB_CATEGORY_MODERATION) is match
