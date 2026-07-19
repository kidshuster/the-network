from __future__ import annotations

import hashlib
import json
import re

import discord

from bot.domain.errors import ProfileParseError
from bot.services.message_formatter import sanitize_author
from bot.services.profile_parser import ParsedProfile, parse_profile

_PROFILE_CARD_VERSION = 3
PROFILE_CARD_FOOTER_PREFIX = "The Network • profile card"

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


def profile_card_footer() -> str:
    return (
        f"{PROFILE_CARD_FOOTER_PREFIX} • v{_PROFILE_CARD_VERSION} • "
        "use Edit Profile below to update"
    )


def _profile_emoji_icon_url(emoji_id: int | None) -> str | None:
    if emoji_id is None:
        return None
    return f"https://cdn.discordapp.com/emojis/{emoji_id}.png?size=128"


def profile_embed_content_signature(embed: discord.Embed) -> str:
    author = embed.author
    payload = {
        "title": embed.title,
        "description": embed.description,
        "author_name": author.name if author else None,
        "author_icon_url": author.icon_url if author else None,
        "fields": [(field.name, field.value, field.inline) for field in embed.fields],
        "footer": embed.footer.text if embed.footer else None,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
    emoji_id: int | None = None,
) -> discord.Embed:
    status = "Enabled" if enabled else "Disabled"
    colour = discord.Colour.green() if enabled else discord.Colour.red()
    embed = discord.Embed(
        description="Server profile for **The Network** relay.",
        colour=colour,
    )
    author_kwargs: dict[str, str] = {"name": sanitize_author(display_name.strip() or server_name)}
    icon_url = _profile_emoji_icon_url(emoji_id)
    if icon_url is not None:
        author_kwargs["icon_url"] = icon_url
    embed.set_author(**author_kwargs)
    embed.add_field(name="Server name", value=server_name, inline=True)
    embed.add_field(name="Source channel", value=f"<#{source_channel_id}>", inline=True)
    embed.add_field(
        name="Network",
        value=f"`{network_key}`" if network_key else "_inferred from feed category_",
        inline=True,
    )
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(
        name="Connect your server",
        value=(
            "On **your** server, open your announcement channel, click **Follow**, "
            f"and select <#{source_channel_id}>. Any message **published** from that "
            "announcement channel is forwarded to the network using this profile card."
        ),
        inline=False,
    )
    embed.set_footer(text=profile_card_footer())
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
    display_name = raw_fields.get("display_name", "").strip()
    if not display_name and embed.author and embed.author.name:
        display_name = embed.author.name.strip()
    if not display_name:
        display_name = (embed.title or "").strip() or server_name

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
