from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from context_helpers import make_test_context
from discord_helpers import make_guild_with_roles

from bot.services.client_profile_edit import apply_client_profile_edit
from bot.testing.png_fixtures import probe_png_bytes


@pytest.mark.asyncio
async def test_apply_edit_not_found(db) -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    context = make_test_context(db)
    bot = MagicMock()

    result = await apply_client_profile_edit(bot, context, guild, client_id=999, display_name="New")

    assert result.success is False
    assert result.error == "Client profile was not found."


@pytest.mark.asyncio
async def test_apply_edit_rejects_empty_display_name(db) -> None:
    from repository_helpers import create_test_client

    guild, _, _, _, _ = make_guild_with_roles()
    context = make_test_context(db)
    client = await create_test_client(context.client_repo)
    bot = MagicMock()

    result = await apply_client_profile_edit(
        bot, context, guild, client_id=client.id, display_name="  "
    )

    assert result.success is False
    assert result.error == "Display name cannot be empty."


@pytest.mark.asyncio
async def test_apply_edit_updates_display_name_and_refreshes_profile(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repository_helpers import create_test_client

    guild, _, _, _, _ = make_guild_with_roles()
    context = make_test_context(db)
    client = await create_test_client(context.client_repo)
    bot = MagicMock()

    refresh = AsyncMock()
    monkeypatch.setattr("bot.services.client_profile_edit.refresh_client_profile_message", refresh)

    result = await apply_client_profile_edit(
        bot, context, guild, client_id=client.id, display_name="Renamed"
    )

    assert result.success is True
    assert result.client is not None
    assert result.client.display_name == "Renamed"
    refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_edit_invalid_image_returns_validation_error(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repository_helpers import create_test_client

    guild, _, _, _, _ = make_guild_with_roles()
    context = make_test_context(db)
    client = await create_test_client(context.client_repo)
    bot = MagicMock()

    attachment = MagicMock(spec=discord.Attachment)
    attachment.size = 100
    attachment.content_type = "image/png"
    attachment.filename = "bad.png"
    attachment.read = AsyncMock(return_value=b"not-an-image")

    monkeypatch.setattr(
        "bot.services.client_profile_edit.refresh_client_profile_message",
        AsyncMock(),
    )

    result = await apply_client_profile_edit(
        bot,
        context,
        guild,
        client_id=client.id,
        display_name="Acme",
        profile_image=attachment,
    )

    assert result.success is False
    assert result.error == "Profile image could not be decoded."


@pytest.mark.asyncio
async def test_apply_edit_with_valid_image_syncs_emoji(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repository_helpers import create_test_client

    guild, _, _, _, _ = make_guild_with_roles()
    context = make_test_context(db)
    client = await create_test_client(context.client_repo)
    bot = MagicMock()

    attachment = MagicMock(spec=discord.Attachment)
    attachment.size = len(probe_png_bytes())
    attachment.content_type = "image/png"
    attachment.filename = "profile.png"
    attachment.read = AsyncMock(return_value=probe_png_bytes())

    emoji_result = MagicMock(
        emoji_id=42,
        emoji_name="acme_emoji",
        image_hash="hash123",
        degraded_reason=None,
        warning=None,
        delete_emoji_id=None,
        skipped=False,
    )
    monkeypatch.setattr(
        "bot.services.emoji_service.EmojiService.sync_for_profile",
        AsyncMock(return_value=emoji_result),
    )
    monkeypatch.setattr(
        "bot.services.client_profile_edit.refresh_client_profile_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.services.emoji_service.EmojiService.delete_emoji",
        AsyncMock(),
    )

    result = await apply_client_profile_edit(
        bot,
        context,
        guild,
        client_id=client.id,
        display_name="Acme",
        profile_image=attachment,
    )

    assert result.success is True
    updated = await context.client_repo.get_by_id(client.id)
    assert updated is not None
    assert updated.emoji_id == 42
    assert updated.emoji_name == "acme_emoji"
