from __future__ import annotations

import logging

from bot.db.repositories import ProfileRepository
from bot.domain.profile import ServerProfile

logger = logging.getLogger(__name__)


class ProfileCache:
    """In-memory cache mapping source channels and forum threads to profiles."""

    def __init__(self, profile_repo: ProfileRepository) -> None:
        self._profile_repo = profile_repo
        self._by_source_channel: dict[int, ServerProfile] = {}
        self._by_thread: dict[int, ServerProfile] = {}

    @property
    def profile_count(self) -> int:
        return len(self._by_thread)

    @property
    def enabled_profile_count(self) -> int:
        return sum(1 for profile in self._by_thread.values() if profile.enabled)

    async def load_cache(self) -> None:
        profiles = await self._profile_repo.list_all()
        self._by_source_channel = {profile.source_channel_id: profile for profile in profiles}
        self._by_thread = {profile.profile_thread_id: profile for profile in profiles}
        logger.info(
            "Profile cache loaded",
            extra={
                "profile_count": len(profiles),
                "enabled_profile_count": self.enabled_profile_count,
            },
        )

    def get_by_source_channel(self, channel_id: int) -> ServerProfile | None:
        return self._by_source_channel.get(channel_id)

    def get_by_thread_id(self, thread_id: int) -> ServerProfile | None:
        return self._by_thread.get(thread_id)

    def get_enabled_by_source_channel(self, channel_id: int) -> ServerProfile | None:
        profile = self.get_by_source_channel(channel_id)
        if profile is None or not profile.enabled:
            return None
        return profile
