from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.db.repositories import ServerRequestRepository
from bot.domain.server_request import ServerRequestStatus
from bot.smoke.provision_flow import (
    cleanup_join_requests_smoke_artifacts,
    cleanup_smoke_join_request_messages,
)


@pytest.mark.asyncio
async def test_cleanup_smoke_join_request_messages_deletes_discord_and_db(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = ServerRequestRepository(db)
    created = await repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=1,
        server_name="Smoke Accept abc",
        display_name="Smoke",
        profile_image_url="https://example.com/p.png",
    )
    await repo.set_moderator_message_id(created.id, 9001)
    await repo.resolve(created.id, status=ServerRequestStatus.APPROVED, resolved_by_user_id=2)

    message = MagicMock(spec=discord.Message)
    message.delete = AsyncMock()

    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)

    guild = MagicMock(spec=discord.Guild)
    context = MagicMock()
    context.server_request_repo = repo

    monkeypatch.setattr(
        "bot.services.guild_layout.resolve_join_requests_channel",
        MagicMock(return_value=channel),
    )

    await cleanup_smoke_join_request_messages(guild, context, [created.id])

    channel.fetch_message.assert_awaited_once_with(9001)
    message.delete.assert_awaited_once()
    assert await repo.get_by_id(created.id) is None


@pytest.mark.asyncio
async def test_cleanup_join_requests_smoke_artifacts_sweeps_channel_and_db(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = ServerRequestRepository(db)
    created = await repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=1,
        server_name="Smoke Accept stale",
        display_name="Smoke",
        profile_image_url="https://example.com/p.png",
    )

    smoke_embed = discord.Embed()
    smoke_embed.add_field(name="Server name", value="Smoke Accept stale", inline=False)
    smoke_message = MagicMock(spec=discord.Message)
    smoke_message.author.id = 42
    smoke_message.embeds = [smoke_embed]
    smoke_message.delete = AsyncMock()

    real_embed = discord.Embed()
    real_embed.add_field(name="Server name", value="Real Server", inline=False)
    real_message = MagicMock(spec=discord.Message)
    real_message.author.id = 42
    real_message.embeds = [real_embed]

    async def history(limit: int = 200):
        yield smoke_message
        yield real_message

    channel = MagicMock(spec=discord.TextChannel)
    channel.history = history

    bot_member = MagicMock(spec=discord.Member)
    bot_member.id = 42

    guild = MagicMock(spec=discord.Guild)
    context = MagicMock()
    context.server_request_repo = repo

    monkeypatch.setattr(
        "bot.services.guild_layout.resolve_join_requests_channel",
        MagicMock(return_value=channel),
    )

    await cleanup_join_requests_smoke_artifacts(guild, context, bot_member)

    smoke_message.delete.assert_awaited_once()
    assert await repo.get_by_id(created.id) is None


@pytest.mark.asyncio
async def test_cleanup_smoke_join_request_messages_skips_missing_message(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = ServerRequestRepository(db)
    created = await repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=1,
        server_name="Smoke Deny abc",
        display_name="Smoke",
        profile_image_url="https://example.com/p.png",
    )
    await repo.set_moderator_message_id(created.id, 9002)

    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "missing"))

    guild = MagicMock(spec=discord.Guild)
    context = MagicMock()
    context.server_request_repo = repo

    monkeypatch.setattr(
        "bot.services.guild_layout.resolve_join_requests_channel",
        MagicMock(return_value=channel),
    )

    await cleanup_smoke_join_request_messages(guild, context, [created.id])

    assert await repo.get_by_id(created.id) is None
