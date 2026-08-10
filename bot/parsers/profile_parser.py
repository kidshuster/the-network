from __future__ import annotations

import re
from dataclasses import dataclass

from bot.domain.errors import ProfileParseError

CHANNEL_MENTION_RE = re.compile(r"^<#(\d+)>$")
SNOWFLAKE_RE = re.compile(r"^\d{17,20}$")
KEY_RE = re.compile(r"^[a-z_]+$")


@dataclass(frozen=True)
class ParsedProfile:
    server_name: str
    source_channel_id: int
    enabled: bool
    network_key: str | None
    display_name: str


def _parse_bool(raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise ProfileParseError(f"Invalid boolean: {raw!r}")


def _parse_channel(raw: str) -> int:
    value = raw.strip()
    mention = CHANNEL_MENTION_RE.match(value)
    if mention:
        return int(mention.group(1))
    if SNOWFLAKE_RE.match(value):
        return int(value)
    raise ProfileParseError(f"Invalid source_channel: {raw!r}")


def parse_profile(content: str, *, thread_name: str = "") -> ParsedProfile:
    """Parse forum profile starter body (YAML-like key: value lines)."""
    fields: dict[str, str] = {}
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ProfileParseError(f"Line {line_no}: expected key: value")
        key_part, _, value_part = line.partition(":")
        key = key_part.strip().lower()
        value = value_part.strip()
        if not KEY_RE.match(key):
            raise ProfileParseError(f"Line {line_no}: invalid key {key!r}")
        if key in fields:
            raise ProfileParseError(f"Duplicate key: {key}")
        fields[key] = value

    server_name = fields.get("server_name", "").strip() or thread_name.strip()
    if not server_name:
        raise ProfileParseError("server_name is missing and thread title fallback is empty.")

    if "source_channel" not in fields:
        raise ProfileParseError("Missing required key: source_channel")
    source_channel_id = _parse_channel(fields["source_channel"])

    if "enabled" not in fields:
        raise ProfileParseError("Missing required key: enabled")
    enabled = _parse_bool(fields["enabled"])

    network_key = fields.get("network", "").strip().lower() or None
    display_name = fields.get("display_name", "").strip() or server_name

    return ParsedProfile(
        server_name=server_name,
        source_channel_id=source_channel_id,
        enabled=enabled,
        network_key=network_key,
        display_name=display_name,
    )
