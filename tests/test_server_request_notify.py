from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.server_request_service import ServerRequestService


def _service(*, bot_user_id: int = 999) -> ServerRequestService:
    bot = MagicMock()
    bot.user = MagicMock(id=bot_user_id)
    context = MagicMock()
    return ServerRequestService(context, bot)


@pytest.mark.asyncio
async def test_notify_requester_skips_bot_self() -> None:
    service = _service(bot_user_id=42)
    requester = MagicMock(spec=discord.Member)
    requester.id = 42
    requester.bot = True
    requester.send = AsyncMock()

    await service._notify_requester(requester, approved=True)

    requester.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_requester_skips_other_bots() -> None:
    service = _service(bot_user_id=1)
    requester = MagicMock(spec=discord.Member)
    requester.id = 2
    requester.bot = True
    requester.send = AsyncMock()

    await service._notify_requester(requester, approved=False)

    requester.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_requester_swallows_http_exception() -> None:
    service = _service(bot_user_id=1)
    requester = MagicMock(spec=discord.Member)
    requester.id = 2
    requester.bot = False
    requester.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "forbidden"))

    await service._notify_requester(requester, approved=True)


@pytest.mark.asyncio
async def test_notify_requester_swallows_attribute_error() -> None:
    service = _service(bot_user_id=1)
    requester = MagicMock(spec=discord.Member)
    requester.id = 2
    requester.bot = False
    requester.send = AsyncMock(
        side_effect=AttributeError("'ClientUser' object has no attribute 'create_dm'")
    )

    await service._notify_requester(requester, approved=False)


@pytest.mark.asyncio
async def test_notify_requester_sends_for_human_user() -> None:
    service = _service(bot_user_id=1)
    requester = MagicMock(spec=discord.Member)
    requester.id = 2
    requester.bot = False
    requester.send = AsyncMock()

    await service._notify_requester(requester, approved=True)

    requester.send.assert_awaited_once()
