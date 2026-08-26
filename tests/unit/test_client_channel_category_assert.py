from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from tests.core.provision_flow import assert_client_channels_under_category


def test_assert_client_channels_under_category_passes() -> None:
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    category.name = "Acme"
    profile = MagicMock(spec=discord.TextChannel, id=30)
    profile.name = "📚-acme-profile"
    profile.category_id = 10
    profile.category = category
    publish = MagicMock(spec=discord.TextChannel, id=40)
    publish.name = "📤-acme-stingers-publish"
    publish.category_id = 10
    publish.category = category

    guild = MagicMock(spec=discord.Guild)
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {10: category, 30: profile, 40: publish}.get(channel_id)
    )

    assert_client_channels_under_category(
        guild,
        client_category_id=10,
        client_server_name="Acme",
        channel_ids={"profile": 30, "publish": 40, "announcements": None},
    )


def test_assert_client_channels_under_category_rejects_wrong_parent() -> None:
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    category.name = "Acme"
    wrong = MagicMock(spec=discord.CategoryChannel, id=99)
    wrong.name = "📢-acme-stingers-announcements"
    announcements = MagicMock(spec=discord.TextChannel, id=50)
    announcements.name = "📢-acme-stingers-announcements"
    announcements.category_id = 99
    announcements.category = wrong

    guild = MagicMock(spec=discord.Guild)
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {10: category, 50: announcements}.get(channel_id)
    )

    with pytest.raises(RuntimeError, match="under category"):
        assert_client_channels_under_category(
            guild,
            client_category_id=10,
            client_server_name="Acme",
            channel_ids={"announcements": 50},
        )


def test_assert_client_channels_under_category_rejects_channel_id_that_is_category() -> None:
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    category.name = "Acme"
    mistaken = MagicMock(spec=discord.CategoryChannel, id=50)
    mistaken.name = "📢-acme-stingers-announcements"

    guild = MagicMock(spec=discord.Guild)
    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {10: category, 50: mistaken}.get(channel_id)
    )

    with pytest.raises(RuntimeError, match="resolved to a category"):
        assert_client_channels_under_category(
            guild,
            client_category_id=10,
            client_server_name="Acme",
            channel_ids={"announcements": 50},
        )
