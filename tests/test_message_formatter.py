from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.domain.client import Client
from bot.services.message_formatter import (
    MENTION_TOKEN_RE,
    build_relay_embed_from_client,
    has_relayable_content,
    client_emoji_url,
    sanitize_author,
    sender_name,
)


def _sample_client(*, emoji_id: int | None = 999) -> Client:
    return Client(
        id=1,
        guild_id=100,
        server_name="test-server",
        display_name="Test Server",
        enabled=True,
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        emoji_id=emoji_id,
        emoji_name="net_test_123456" if emoji_id else None,
        image_hash="abc",
        degraded_reason=None,
    )


def _message(*, content: str = "Hello", author_name: str = "Alice") -> discord.Message:
    message = MagicMock(spec=discord.Message)
    message.content = content
    message.embeds = []
    message.attachments = []
    author = MagicMock()
    author.name = author_name
    author.display_name = author_name
    message.author = author
    return message


def test_client_emoji_url() -> None:
    client = _sample_client()
    assert client_emoji_url(client) == "https://cdn.discordapp.com/emojis/999.png?size=128"
    assert client_emoji_url(_sample_client(emoji_id=None)) is None


def test_build_relay_embed_uses_display_name_and_server_icon() -> None:
    client = _sample_client()
    message = _message(content="Raid starts at 8 PM.", author_name="1 test #stingers")
    parts = build_relay_embed_from_client(message, client)
    embed = parts.embed

    assert embed.author.name == "Test Server"
    assert embed.author.icon_url == client_emoji_url(client)
    assert embed.description == "Raid starts at 8 PM."
    assert parts.primary_image_url is None


def test_build_relay_embed_includes_image() -> None:
    client = _sample_client()
    message = _message(content="")
    attachment = MagicMock(spec=discord.Attachment)
    attachment.url = "https://cdn.discordapp.com/attachments/1/2/image.png"
    attachment.content_type = "image/png"
    attachment.filename = "image.png"
    message.attachments = [attachment]

    parts = build_relay_embed_from_client(message, client)

    assert parts.primary_image_url == attachment.url
    assert parts.embed.image.url == attachment.url


def test_has_relayable_content_accepts_image_only() -> None:
    message = _message(content="")
    attachment = MagicMock(spec=discord.Attachment)
    attachment.url = "https://cdn.discordapp.com/attachments/1/2/image.png"
    attachment.content_type = "image/png"
    attachment.filename = "image.png"
    message.attachments = [attachment]

    assert has_relayable_content(message) is True


def test_sender_name_sanitized() -> None:
    message = _message(author_name="@everyone Evil <@123456789>")
    assert MENTION_TOKEN_RE.search(sender_name(message)) is None
    assert "@everyone" not in sender_name(message)


def test_sanitize_author_mention_injection() -> None:
    assert "@everyone" not in sanitize_author("@everyone Evil")
    assert "<@123456789>" not in sanitize_author("Evil <@123456789>")
    assert "<@&987654321>" not in sanitize_author("Role <@&987654321>")
