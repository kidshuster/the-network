from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass

import discord

from bot.constants import DEGRADED_FALLBACK
from bot.core.models.client import Client
from bot.messages.loader import relay_embed_spec, resolve_colour

logger = logging.getLogger(__name__)

MENTION_TOKEN_RE = re.compile(r"<@[!&]?\d+>")
EVERYONE_HERE_RE = re.compile(r"@everyone|@here", re.IGNORECASE)
MAX_AUTHOR_LEN = 64
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def sanitize_author(name: str) -> str:
    """Strip mention patterns from relay display names."""
    cleaned = name.strip()
    cleaned = EVERYONE_HERE_RE.sub("", cleaned)
    cleaned = MENTION_TOKEN_RE.sub("", cleaned)
    cleaned = re.sub(r"@(?!\u200b)", "@\u200b", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > MAX_AUTHOR_LEN:
        cleaned = cleaned[:MAX_AUTHOR_LEN]
    return cleaned


def client_display_name(client: Client) -> str:
    return sanitize_author(client.display_name.strip() or client.server_name.strip())


def client_emoji_url(client: Client) -> str | None:
    if client.emoji_id is None:
        return None
    return f"https://cdn.discordapp.com/emojis/{client.emoji_id}.png?size=128"


def sender_name(message: discord.Message) -> str:
    return sanitize_author(message.author.display_name or message.author.name)


def _attachment_is_image(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True
    return attachment.filename.lower().endswith(_IMAGE_EXTENSIONS)


def extract_relay_body(message: discord.Message) -> str:
    """Return relayable text from message content or embed fields."""
    content = message.content.strip()
    if content:
        return content

    parts: list[str] = []
    for embed in message.embeds:
        if embed.title:
            parts.append(embed.title.strip())
        if embed.description:
            parts.append(embed.description.strip())
        for field in embed.fields:
            if field.name:
                parts.append(field.name.strip())
            if field.value:
                parts.append(field.value.strip())
    return "\n\n".join(part for part in parts if part).strip()


def extract_relay_image_urls(message: discord.Message) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def add(url: str | None) -> None:
        if url and url not in seen:
            seen.add(url)
            urls.append(url)

    for attachment in message.attachments:
        if _attachment_is_image(attachment):
            add(attachment.url)

    for embed in message.embeds:
        if embed.image and embed.image.url:
            add(embed.image.url)
        if embed.thumbnail and embed.thumbnail.url:
            add(embed.thumbnail.url)

    return urls


def has_relayable_content(message: discord.Message) -> bool:
    if extract_relay_body(message).strip():
        return True
    if extract_relay_image_urls(message):
        return True
    if message.attachments:
        return True
    return False


@dataclass(frozen=True)
class RelayEmbedParts:
    embed: discord.Embed
    primary_image_url: str | None


def build_relay_embed_from_client(message: discord.Message, client: Client) -> RelayEmbedParts:
    shell = relay_embed_spec()
    body = extract_relay_body(message)
    if client.timecode_enabled and body:
        try:
            from bot.core.parsers.date_parser import replace_dates

            body = replace_dates(body)
        except Exception:
            logger.exception(
                "Date/time conversion failed; relaying original text",
                extra={"client_id": client.id},
            )
    image_urls = extract_relay_image_urls(message)
    primary_image_url = image_urls[0] if image_urls else None

    colour = resolve_colour(shell.colour)
    embed = discord.Embed(description=body or None, colour=colour)

    author_name = client_display_name(client)
    author_kwargs: dict[str, str] = {"name": author_name}
    icon_url = client_emoji_url(client)
    if icon_url is not None:
        author_kwargs["icon_url"] = icon_url
    elif shell.degraded_emoji_prefix and client.emoji_id is None:
        author_kwargs["name"] = f"{DEGRADED_FALLBACK} {author_name}"
    embed.set_author(**author_kwargs)

    if primary_image_url is not None:
        embed.set_image(url=primary_image_url)
    return RelayEmbedParts(embed=embed, primary_image_url=primary_image_url)


@dataclass(frozen=True)
class RelayPayload:
    embed: discord.Embed
    files: tuple[discord.File, ...] = ()


async def build_relay_payload_from_client(
    message: discord.Message,
    client: Client,
) -> RelayPayload:
    parts = build_relay_embed_from_client(message, client)
    files: list[discord.File] = []
    skip_url = parts.primary_image_url
    for attachment in message.attachments:
        if skip_url is not None and attachment.url == skip_url:
            continue
        try:
            data = await attachment.read()
        except discord.HTTPException:
            continue
        if not data:
            continue
        files.append(discord.File(fp=io.BytesIO(data), filename=attachment.filename))
    return RelayPayload(embed=parts.embed, files=tuple(files))


async def build_system_announcement_payload(
    message: discord.Message,
    *,
    body: str,
) -> RelayPayload:
    embed = discord.Embed(description=body or None, colour=resolve_colour("blurple"))
    embed.set_author(name="The Network")
    image_urls = extract_relay_image_urls(message)
    if image_urls:
        embed.set_image(url=image_urls[0])
    files: list[discord.File] = []
    for attachment in message.attachments:
        if image_urls and attachment.url == image_urls[0]:
            continue
        try:
            data = await attachment.read()
        except discord.HTTPException:
            continue
        if data:
            files.append(discord.File(fp=io.BytesIO(data), filename=attachment.filename))
    return RelayPayload(embed=embed, files=tuple(files))
