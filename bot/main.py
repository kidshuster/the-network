from __future__ import annotations

import asyncio
import logging
import sys

from bot.app.bot import NetworkRelayBot
from bot.config import Settings
from bot.logging_config import configure_logging

logger = logging.getLogger(__name__)


def _validate_test_mode(settings: Settings) -> None:
    if not settings.enable_test_commands:
        return
    logger.warning(
        "TEST COMMANDS ENABLED — /server test is registered for the test guild only",
        extra={
            "test_guild_id": settings.test_guild_id,
            "guild_id": settings.guild_id,
        },
    )
    import importlib

    try:
        importlib.import_module(".".join(("tests", "core")))
        importlib.import_module(".".join(("tests", "core", "smoke_api")))
    except ImportError as exc:
        raise SystemExit(
            "ENABLE_TEST_COMMANDS=true but the development tests package is unavailable. "
            "Use a development install (pip install -e '.[dev]') via bin/test-bot.sh."
        ) from exc


async def run_bot() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    _validate_test_mode(settings)
    logger.info(
        "Starting The Network relay bot",
        extra={
            "guild_id": settings.guild_id,
            "database_path": str(settings.database_path),
            "enable_test_commands": settings.enable_test_commands,
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
