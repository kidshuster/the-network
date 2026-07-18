from __future__ import annotations

import re

import discord

from bot.domain.errors import ProfileParseError
from bot.services.profile_parser import ParsedProfile, parse_profile

_CHANNEL_MENTION_RE = re.compile(r"^<#(\d+)>$")
_SNOWFLAKE_RE = re.compile(r"^\d{17,20}$")

_EMBED_FIELD_ALIASES: dict[str, str] = {
    "server": "server_name",
    "server name": "server_name",
    "source channel": "source_channel",
    "source_channel": "source_channel",
    "network": "network",
    "display name": "display_name",
    "display_name": "display_name",
    "status": "enabled",
    "enabled": "enabled",
}


def format_profile_yaml(
    *,
    server_name: str,
    display_name: str,
    source_channel_id: int,
    network_key: str | None,
    enabled: bool,
) -> str:
    lines = [
        f"server_name: {server_name}",
        f"source_channel: <#{source_channel_id}>",
        f"enabled: {'true' if enabled else 'false'}",
    ]
    if network_key:
        lines.append(f"network: {network_key}")
    if display_name != server_name:
        lines.append(f"display_name: {display_name}")
    return "\n".join(lines)


def build_profile_embed(
    *,
    server_name: str,
    display_name: str,
    source_channel_id: int,
    network_key: str | None,
    enabled: bool,
) -> discord.Embed:
    status = "Enabled" if enabled else "Disabled"
    colour = discord.Colour.green() if enabled else discord.Colour.red()
    embed = discord.Embed(
        title=display_name,
        description="Server profile for **The Network** relay.",
        colour=colour,
    )
    embed.add_field(name="Server name", value=server_name, inline=True)
    embed.add_field(name="Source channel", value=f"<#{source_channel_id}>", inline=True)
    embed.add_field(
        name="Network",
        value=f"`{network_key}`" if network_key else "_inferred from feed category_",
        inline=True,
    )
    embed.add_field(name="Display name", value=display_name, inline=True)
    embed.add_field(name="Status", value=status, inline=True)
    embed.set_image(url="attachment://profile.png")
    embed.set_footer(text="The Network • managed by /server commands")
    return embed


def _parse_bool_label(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "enabled", "yes", "on"}:
        return True
    if lowered in {"false", "disabled", "no", "off"}:
        return False
    raise ProfileParseError(f"Invalid enabled/status value: {value!r}")


def _parse_channel_value(value: str) -> int:
    cleaned = value.strip()
    mention = _CHANNEL_MENTION_RE.match(cleaned)
    if mention:
        return int(mention.group(1))
    if _SNOWFLAKE_RE.match(cleaned):
        return int(cleaned)
    raise ProfileParseError(f"Invalid source channel in embed: {value!r}")


def _clean_network_key(value: str) -> str | None:
    cleaned = value.strip().strip("`").strip()
    if not cleaned or cleaned.startswith("_"):
        return None
    return cleaned.lower()


def parse_profile_embed(embed: discord.Embed, *, thread_name: str = "") -> ParsedProfile:
    """Parse profile config from a structured forum starter embed."""
    raw_fields: dict[str, str] = {}
    for field in embed.fields:
        name = field.name
        value = field.value
        if name is None or value is None:
            continue
        key = _EMBED_FIELD_ALIASES.get(name.strip().lower())
        if key is None:
            continue
        raw_fields[key] = value.strip()

    server_name = raw_fields.get("server_name", "").strip()
    if not server_name:
        title = (embed.title or "").strip()
        server_name = title or thread_name.strip()
    if not server_name:
        raise ProfileParseError("Profile embed is missing server name.")

    if "source_channel" not in raw_fields:
        raise ProfileParseError("Profile embed is missing source channel.")
    source_channel_id = _parse_channel_value(raw_fields["source_channel"])

    if "enabled" in raw_fields:
        enabled = _parse_bool_label(raw_fields["enabled"])
    else:
        enabled = True

    network_key = _clean_network_key(raw_fields.get("network", ""))
    display_name = raw_fields.get("display_name", "").strip() or server_name

    return ParsedProfile(
        server_name=server_name,
        source_channel_id=source_channel_id,
        enabled=enabled,
        network_key=network_key,
        display_name=display_name,
    )


def parse_starter_message(message: discord.Message, *, thread_name: str = "") -> ParsedProfile:
    """Parse profile config from embed-first starter messages, with YAML fallback."""
    content = (message.content or "").strip()
    if message.embeds:
        try:
            return parse_profile_embed(message.embeds[0], thread_name=thread_name)
        except ProfileParseError:
            if content:
                return parse_profile(content, thread_name=thread_name)
            raise
    if not content or content == "\u200b":
        raise ProfileParseError("Profile starter message has no embed or YAML body.")
    return parse_profile(content, thread_name=thread_name)
