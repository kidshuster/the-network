from __future__ import annotations

from unittest.mock import MagicMock

import discord

from bot.domain.profile import ServerProfile
from bot.services.message_formatter import (
    MENTION_TOKEN_RE,
    build_relay_embed,
    has_relayable_content,
    profile_emoji_url,
    sanitize_author,
    sender_name,
)


def _sample_profile(
    *,
    emoji_id: int | None = 999,
    emoji_name: str | None = "net_test_123456",
) -> ServerProfile:
    return ServerProfile(
        id=1,
        guild_id=100,
        profile_thread_id=301,
        profile_starter_message_id=302,
        source_channel_id=201,
        network_id=10,
        server_name="test-server",
        display_name="Test Server",
        enabled=True,
        emoji_id=emoji_id,
        emoji_name=emoji_name,
        image_hash="abc",
        degraded_reason=None,
        partner_role_id=None,
        profile_forum_channel_id=None,
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


def test_profile_emoji_url() -> None:
    profile = _sample_profile()
    assert profile_emoji_url(profile) == "https://cdn.discordapp.com/emojis/999.png?size=128"
    assert profile_emoji_url(_sample_profile(emoji_id=None, emoji_name=None)) is None


def test_build_relay_embed_uses_display_name_and_server_icon() -> None:
    profile = _sample_profile()
    message = _message(content="Raid starts at 8 PM.", author_name="1 test #stingers")
    parts = build_relay_embed(message, profile)
    embed = parts.embed

    assert embed.author.name == "Test Server"
    assert embed.author.icon_url == profile_emoji_url(profile)
    assert embed.description == "Raid starts at 8 PM."
    assert parts.primary_image_url is None


def test_build_relay_embed_includes_image() -> None:
    profile = _sample_profile()
    message = _message(content="")
    attachment = MagicMock(spec=discord.Attachment)
    attachment.url = "https://cdn.discordapp.com/attachments/1/2/image.png"
    attachment.content_type = "image/png"
    attachment.filename = "image.png"
    message.attachments = [attachment]

    parts = build_relay_embed(message, profile)

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
