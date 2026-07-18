from __future__ import annotations

import pytest

from bot.domain.errors import ProfileParseError
from bot.services.profile_parser import parse_profile

DESIGN_SPEC_SAMPLE = """\
server_name: Vanguard
source_channel: <#123456789012345678>
enabled: true
network: stingers
display_name: Vanguard
"""


def test_valid_design_spec_sample() -> None:
    profile = parse_profile(DESIGN_SPEC_SAMPLE)
    assert profile.server_name == "Vanguard"
    assert profile.source_channel_id == 123456789012345678
    assert profile.enabled is True
    assert profile.network_key == "stingers"
    assert profile.display_name == "Vanguard"


def test_case_insensitive_keys() -> None:
    body = """\
Server_Name: Alpha
SOURCE_CHANNEL: 123456789012345678
ENABLED: false
"""
    profile = parse_profile(body)
    assert profile.server_name == "Alpha"
    assert profile.enabled is False


def test_channel_mention_and_raw_id() -> None:
    profile_mention = parse_profile(
        "source_channel: <#987654321098765432>\nenabled: true\n",
        thread_name="T",
    )
    assert profile_mention.source_channel_id == 987654321098765432

    profile_raw = parse_profile(
        "source_channel: 111111111111111111\nenabled: true\n",
        thread_name="T",
    )
    assert profile_raw.source_channel_id == 111111111111111111


def test_thread_name_fallback() -> None:
    profile = parse_profile(
        "source_channel: 123456789012345678\nenabled: true\n",
        thread_name="Fallback Server",
    )
    assert profile.server_name == "Fallback Server"
    assert profile.display_name == "Fallback Server"


def test_display_name_fallback() -> None:
    profile = parse_profile(
        "server_name: MyServer\nsource_channel: 123456789012345678\nenabled: true\n"
    )
    assert profile.display_name == "MyServer"


def test_comments_and_blank_lines() -> None:
    body = """\
# profile config
server_name: Beta

source_channel: <#123456789012345678>
enabled: true
"""
    profile = parse_profile(body)
    assert profile.server_name == "Beta"


def test_duplicate_key_rejected() -> None:
    body = """\
server_name: One
server_name: Two
source_channel: 123456789012345678
enabled: true
"""
    with pytest.raises(ProfileParseError, match="Duplicate"):
        parse_profile(body)


def test_invalid_boolean_rejected() -> None:
    body = """\
server_name: X
source_channel: 123456789012345678
enabled: maybe
"""
    with pytest.raises(ProfileParseError, match="boolean"):
        parse_profile(body)


def test_invalid_channel_rejected() -> None:
    body = """\
server_name: X
source_channel: not-a-channel
enabled: true
"""
    with pytest.raises(ProfileParseError, match="source_channel"):
        parse_profile(body)
