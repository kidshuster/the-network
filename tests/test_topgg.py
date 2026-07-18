from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.services.topgg import TopggService


@pytest.mark.asyncio
async def test_post_stats_success() -> None:
    bot = MagicMock()
    bot.user = MagicMock(id=123456789)
    bot.guilds = [MagicMock(), MagicMock()]

    response = AsyncMock()
    response.status = 200
    response.text = AsyncMock(return_value="")
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.post = MagicMock(return_value=response)

    service = TopggService(bot, "test-token")
    service._session = session

    assert await service.post_stats() is True
    session.post.assert_called_once()
    call_kwargs = session.post.call_args.kwargs
    assert call_kwargs["json"] == {"server_count": 2}
    assert call_kwargs["headers"]["Authorization"] == "test-token"


@pytest.mark.asyncio
async def test_post_stats_handles_http_error() -> None:
    bot = MagicMock()
    bot.user = MagicMock(id=123456789)
    bot.guilds = []

    response = AsyncMock()
    response.status = 401
    response.text = AsyncMock(return_value="Unauthorized")
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.post = MagicMock(return_value=response)

    service = TopggService(bot, "bad-token")
    service._session = session

    assert await service.post_stats() is False
