from __future__ import annotations

import discord
import pytest

from bot.domain.errors import ProfileParseError
from bot.services.profile_post import (
    build_profile_embed,
    parse_profile_embed,
    parse_starter_message,
)


def test_build_and_parse_profile_embed_roundtrip() -> None:
    embed = build_profile_embed(
        server_name="Vanguard",
        display_name="Vanguard Ops",
        source_channel_id=123456789012345678,
        network_key="stingers",
        enabled=True,
    )
    parsed = parse_profile_embed(embed, thread_name="Fallback")
    assert parsed.server_name == "Vanguard"
    assert parsed.display_name == "Vanguard Ops"
    assert parsed.source_channel_id == 123456789012345678
    assert parsed.network_key == "stingers"
    assert parsed.enabled is True


def test_parse_starter_message_prefers_embed() -> None:
    embed = build_profile_embed(
        server_name="Alpha",
        display_name="Alpha",
        source_channel_id=987654321098765432,
        network_key="stingers",
        enabled=False,
    )

    class FakeMessage:
        content = "server_name: Wrong\nsource_channel: <#1>\nenabled: true\n"
        embeds = [embed]

    parsed = parse_starter_message(FakeMessage(), thread_name="Alpha")
    assert parsed.server_name == "Alpha"
    assert parsed.enabled is False


def test_parse_starter_message_yaml_fallback() -> None:
    body = (
        "server_name: Beta\n"
        "source_channel: <#123456789012345678>\n"
        "enabled: true\n"
        "network: stingers\n"
    )

    class FakeMessage:
        content = body
        embeds: list[discord.Embed] = []

    parsed = parse_starter_message(FakeMessage(), thread_name="Beta")
    assert parsed.server_name == "Beta"
    assert parsed.network_key == "stingers"


def test_parse_starter_message_requires_content_or_embed() -> None:
    class EmptyMessage:
        content = ""
        embeds: list[discord.Embed] = []

    with pytest.raises(ProfileParseError):
        parse_starter_message(EmptyMessage(), thread_name="X")
