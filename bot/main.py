from __future__ import annotations

import asyncio
import logging
import sys

from bot.client import NetworkRelayBot
from bot.config import Settings
from bot.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    logger.info(
        "Starting The Network relay bot",
        extra={
            "guild_id": settings.guild_id,
            "database_path": str(settings.database_path),
        },
    )
    bot = NetworkRelayBot(settings)
    try:
        await bot.start(settings.discord_token)
    finally:
        if not bot.is_closed():
            await bot.close()


def cli_main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception:
        logger.exception("Fatal bot error")
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
