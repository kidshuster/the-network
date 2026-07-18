from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
from discord.ext import tasks

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)


class TopggService:
    """Post guild count statistics to top.gg."""

    def __init__(self, bot: NetworkRelayBot, token: str) -> None:
        self._bot = bot
        self._token = token
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
        await self._bot.wait_until_ready()
        await self.post_stats()
        if not self._autopost.is_running():
            self._autopost.start()
        logger.info("top.gg stats autopost enabled")

    async def close(self) -> None:
        if self._autopost.is_running():
            self._autopost.cancel()
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def post_stats(self) -> bool:
        if self._session is None or self._bot.user is None:
            return False

        url = f"https://top.gg/api/bots/{self._bot.user.id}/stats"
        payload = {"server_count": len(self._bot.guilds)}
        headers = {
            "Authorization": self._token,
            "Content-Type": "application/json",
        }

        try:
            async with self._session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    logger.info(
                        "Posted top.gg server count",
                        extra={"server_count": payload["server_count"]},
                    )
                    return True
                body = await response.text()
                logger.warning(
                    "top.gg stats post failed",
                    extra={
                        "status": response.status,
                        "body": body[:500],
                    },
                )
        except aiohttp.ClientError as exc:
            logger.warning(
                "top.gg stats post error",
                extra={"error": str(exc)},
            )
        return False

    @tasks.loop(minutes=30)
    async def _autopost(self) -> None:
        await self.post_stats()

    @_autopost.before_loop
    async def _wait_for_ready(self) -> None:
        await self._bot.wait_until_ready()
