from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from bot.features.channels.resolve import (
    CATEGORY_LEADERS,
    CATEGORY_MODERATION,
    CATEGORY_NETWORK,
    CHANNEL_CHANGELOG,
    CHANNEL_JOIN_REQUESTS,
    CHANNEL_NETWORK_ANNOUNCEMENTS,
    ChannelLookupError,
    find_channel,
    require_channel,
    resolve_announcement_channel_in_category,
    resolve_bot_role,
    resolve_changelog_channel,
    resolve_human_moderator_role,
    resolve_moderator_role,
    resolve_network_announcements_channel,
    resolve_network_hub_category,
)


def test_find_channel_prefers_canonical_name_and_respects_category() -> None:
    guild = MagicMock(spec=discord.Guild)
    legacy = MagicMock(spec=discord.TextChannel)
    legacy.name = "leaders"
    legacy.category_id = 10
    canonical = MagicMock(spec=discord.TextChannel)
    canonical.name = "leaders-channel"
    canonical.category_id = 10
    elsewhere = MagicMock(spec=discord.TextChannel)
    elsewhere.name = "leaders-channel"
    elsewhere.category_id = 20
    guild.text_channels = [legacy, elsewhere, canonical]

    assert (
        find_channel(
            guild,
            ("leaders-channel", "leaders"),
            channel_type=discord.TextChannel,
            category_id=10,
        )
        is canonical
    )


def test_find_channel_returns_none_when_configuration_is_absent() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.text_channels = []
    assert (
        find_channel(guild, "removed-channel", channel_type=discord.TextChannel)
        is None
    )


def test_require_channel_raises_user_facing_lookup_error() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.text_channels = []
    with pytest.raises(ChannelLookupError) as caught:
        require_channel(guild, "join-requests", channel_type=discord.TextChannel)
    assert caught.value.code == "channel_not_found"
    assert "/server init" in caught.value.message


def test_resolve_network_hub_category() -> None:
    guild = MagicMock(spec=discord.Guild)
    match = MagicMock(spec=discord.CategoryChannel)
    match.name = CATEGORY_NETWORK
    guild.categories = [match]
    assert resolve_network_hub_category(guild) is match


def test_resolve_human_moderator_role_prefers_moderator() -> None:
    guild = MagicMock(spec=discord.Guild)
    bot_role = MagicMock(spec=discord.Role)
    bot_role.name = "The Network"
    human = MagicMock(spec=discord.Role)
    human.name = "Moderator"
    guild.roles = [bot_role, human]
    assert resolve_human_moderator_role(guild) is human


def test_resolve_bot_role_finds_network() -> None:
    guild = MagicMock(spec=discord.Guild)
    legacy = MagicMock(spec=discord.Role)
    legacy.name = "Moderator"
    network = MagicMock(spec=discord.Role)
    network.name = "The Network"
    guild.roles = [legacy, network]
    assert resolve_bot_role(guild) is network


def test_resolve_moderator_role_is_bot_role_alias() -> None:
    guild = MagicMock(spec=discord.Guild)
    role = MagicMock(spec=discord.Role)
    role.name = "The Network"
    guild.roles = [role]
    assert resolve_moderator_role(guild) is role


def test_join_requests_channel_name_constant() -> None:
    assert CHANNEL_JOIN_REQUESTS == "join-requests"


def test_resolve_changelog_channel_only_in_leaders_category() -> None:
    guild = MagicMock(spec=discord.Guild)
    leaders_category = MagicMock(spec=discord.CategoryChannel)
    leaders_category.name = CATEGORY_LEADERS
    leaders_category.id = 10

    in_leaders = MagicMock(spec=discord.TextChannel)
    in_leaders.name = CHANNEL_CHANGELOG
    in_leaders.category_id = leaders_category.id

    elsewhere = MagicMock(spec=discord.TextChannel)
    elsewhere.name = CHANNEL_CHANGELOG
    elsewhere.category_id = 99

    guild.categories = [leaders_category]
    guild.text_channels = [elsewhere, in_leaders]

    assert resolve_changelog_channel(guild) is in_leaders


def test_resolve_network_announcements_channel_uses_regular_text_channel() -> None:
    guild = MagicMock(spec=discord.Guild)
    mod_category = MagicMock(spec=discord.CategoryChannel)
    mod_category.name = CATEGORY_MODERATION
    mod_category.id = 10

    plain = MagicMock(spec=discord.TextChannel)
    plain.name = CHANNEL_NETWORK_ANNOUNCEMENTS
    plain.category_id = mod_category.id
    plain.is_news = MagicMock(return_value=False)

    announcement = MagicMock(spec=discord.TextChannel)
    announcement.name = CHANNEL_NETWORK_ANNOUNCEMENTS
    announcement.category_id = mod_category.id
    announcement.is_news = MagicMock(return_value=True)

    guild.categories = [mod_category]
    guild.text_channels = [plain, announcement]

    assert resolve_network_announcements_channel(guild) is plain

    guild.text_channels = [announcement]
    assert resolve_network_announcements_channel(guild) is None


def test_resolve_announcement_channel_in_category_ignores_plain_text() -> None:
    guild = MagicMock(spec=discord.Guild)
    plain = MagicMock(spec=discord.TextChannel)
    plain.name = CHANNEL_NETWORK_ANNOUNCEMENTS
    plain.category_id = 10
    plain.is_news = MagicMock(return_value=False)
    guild.text_channels = [plain]

    assert (
        resolve_announcement_channel_in_category(
            guild,
            name=CHANNEL_NETWORK_ANNOUNCEMENTS,
            category_id=10,
        )
        is None
    )
