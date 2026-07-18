from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.emoji_service import EmojiService, build_emoji_name, sanitize_slug

SAMPLE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_sanitize_slug() -> None:
    assert sanitize_slug("Vanguard Ops!") == "vanguard_ops"


def test_build_emoji_name_pattern() -> None:
    name = build_emoji_name("vanguard_ops", 123456789012345678)
    assert name == "net_vanguard_ops_345678"
    assert len(name) <= 32


def test_build_emoji_name_collision_suffix() -> None:
    used = {"net_vanguard_ops_345678"}
    name = build_emoji_name("vanguard_ops", 123456789012345678, used_names=used)
    assert name != "net_vanguard_ops_345678"
    assert "_2" in name


@pytest.mark.asyncio
async def test_sync_degrades_on_guild_emoji_cap() -> None:
    service = EmojiService()
    guild = MagicMock(spec=discord.Guild)

    async def raise_cap(**kwargs: object) -> None:
        exc = discord.HTTPException(MagicMock(), "emoji max")
        exc.code = 30008
        raise exc

    guild.create_custom_emoji = AsyncMock(side_effect=raise_cap)

    profile = MagicMock()
    profile.server_name = "Partner"
    profile.display_name = "Partner"
    profile.source_channel_id = 201
    profile.emoji_id = None
    profile.emoji_name = None
    profile.image_hash = None
    profile.degraded_reason = None

    image = MagicMock()
    image.image_hash = "abc123"
    image.data = SAMPLE_PNG

    result = await service.sync_for_profile(
        guild,
        profile,
        image,
        previous_hash=None,
        previous_emoji_id=None,
    )
    assert result.emoji_id is None
    assert result.degraded_reason is not None
    assert result.warning is not None


@pytest.mark.asyncio
async def test_sync_degrades_on_missing_permissions() -> None:
    service = EmojiService()
    guild = MagicMock(spec=discord.Guild)

    async def raise_forbidden(**kwargs: object) -> None:
        exc = discord.HTTPException(MagicMock(), "missing perms")
        exc.code = 50013
        raise exc

    guild.create_custom_emoji = AsyncMock(side_effect=raise_forbidden)

    profile = MagicMock()
    profile.server_name = "Partner"
    profile.display_name = "Partner"
    profile.source_channel_id = 201
    profile.emoji_id = None
    profile.emoji_name = None
    profile.image_hash = None
    profile.degraded_reason = None

    image = MagicMock()
    image.image_hash = "abc123"
    image.data = SAMPLE_PNG

    result = await service.sync_for_profile(
        guild,
        profile,
        image,
        previous_hash=None,
        previous_emoji_id=None,
    )
    assert result.emoji_id is None
    assert result.degraded_reason is not None
    assert "Manage Expressions" in (result.warning or "")


@pytest.mark.asyncio
async def test_sync_recreates_when_emoji_missing_from_guild() -> None:
    service = EmojiService()
    guild = MagicMock(spec=discord.Guild)
    guild.emojis = []
    guild.create_custom_emoji = AsyncMock(
        return_value=MagicMock(id=555, name="net_partner_000201")
    )

    profile = MagicMock()
    profile.server_name = "Partner"
    profile.display_name = "Partner"
    profile.source_channel_id = 201
    profile.emoji_id = 999
    profile.emoji_name = "net_partner_000201"
    profile.image_hash = "same-hash"
    profile.degraded_reason = None

    image = MagicMock()
    image.image_hash = "same-hash"
    image.data = SAMPLE_PNG

    result = await service.sync_for_profile(
        guild,
        profile,
        image,
        previous_hash="same-hash",
        previous_emoji_id=999,
    )
    assert result.skipped is False
    assert result.recreated is True
    guild.create_custom_emoji.assert_called_once()


@pytest.mark.asyncio
async def test_sync_skips_when_hash_unchanged() -> None:
    service = EmojiService()
    guild = MagicMock(spec=discord.Guild)
    guild.emojis = [MagicMock(id=999, name="net_partner_000201")]

    profile = MagicMock()
    profile.server_name = "Partner"
    profile.display_name = "Partner"
    profile.source_channel_id = 201
    profile.emoji_id = 999
    profile.emoji_name = "net_partner_000201"
    profile.image_hash = "same-hash"
    profile.degraded_reason = None

    image = MagicMock()
    image.image_hash = "same-hash"
    image.data = SAMPLE_PNG

    result = await service.sync_for_profile(
        guild,
        profile,
        image,
        previous_hash="same-hash",
        previous_emoji_id=999,
    )
    assert result.skipped is True
    guild.create_custom_emoji.assert_not_called()
