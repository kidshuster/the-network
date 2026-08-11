from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from bot.features.channels import resources
from bot.features.channels.layout.loader import clear_layout_cache


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    clear_layout_cache()
    yield
    clear_layout_cache()


def test_resources_name_returns_yaml_display_name() -> None:
    assert resources.name(resources.ADMIN) == "admin"
    assert resources.name(resources.MODERATION) == "Moderation"


def test_resources_find_and_require_channel() -> None:
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "admin"
    channel.category_id = None
    channel.is_news = MagicMock(return_value=False)
    guild.text_channels = [channel]

    assert resources.find_channel(guild, resources.ADMIN) is channel
    assert resources.require_channel(guild, resources.ADMIN) is channel


def test_resources_require_channel_raises() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.text_channels = []
    with pytest.raises(resources.ResourceLookupError, match="admin"):
        resources.require_channel(guild, resources.ADMIN)
