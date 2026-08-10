from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.constants import SETTING_PROFILE_FORUM_CHANNEL_ID
from bot.db.repositories import SettingsRepository

if TYPE_CHECKING:
    from bot.config import Settings

logger = logging.getLogger(__name__)


class BotSettingsService:
    """Runtime bot settings persisted in SQLite with env fallbacks."""

    def __init__(self, repo: SettingsRepository, env_settings: Settings) -> None:
        self._repo = repo
        self._env_settings = env_settings
        self._profile_forum_channel_id: int | None = None

    async def load(self) -> None:
        stored = await self._repo.get(SETTING_PROFILE_FORUM_CHANNEL_ID)
        if stored is not None:
            self._profile_forum_channel_id = int(stored)
        else:
            self._profile_forum_channel_id = self._env_settings.profile_forum_channel_id
        logger.info(
            "Bot settings loaded",
            extra={"profile_forum_channel_id": self._profile_forum_channel_id},
        )

    @property
    def profile_forum_channel_id(self) -> int | None:
        return self._profile_forum_channel_id

    async def set_profile_forum_channel_id(self, channel_id: int) -> None:
        await self._repo.set(SETTING_PROFILE_FORUM_CHANNEL_ID, str(channel_id))
        self._profile_forum_channel_id = channel_id
        logger.info(
            "Profile forum channel updated",
            extra={"profile_forum_channel_id": channel_id},
        )
