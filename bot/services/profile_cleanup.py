from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from bot.db.repositories import NetworkRepository, ProfileRepository, RelayRecordRepository
from bot.domain.profile import ServerProfile
from bot.services.discord_cleanup import delete_channel, delete_role
from bot.services.emoji_service import EmojiService
from bot.services.profile_cache import ProfileCache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProfileCleanupResult:
    profile: ServerProfile
    deleted_feed: bool
    deleted_profile_channel: bool
    deleted_role: bool
    deleted_emoji: bool
    deleted_record: bool


class ProfileCleanupService:
    """Remove server feed, profile channel, role, emoji, and DB row together."""

    def __init__(
        self,
        profile_repo: ProfileRepository,
        network_repo: NetworkRepository,
        profile_cache: ProfileCache,
        emoji_service: EmojiService,
        relay_record_repo: RelayRecordRepository,
    ) -> None:
        self._profile_repo = profile_repo
        self._network_repo = network_repo
        self._profile_cache = profile_cache
        self._emoji_service = emoji_service
        self._relay_records = relay_record_repo
        self._in_progress: set[int] = set()

    async def cleanup_by_profile_channel_id(
        self,
        guild: discord.Guild,
        channel_id: int,
    ) -> ProfileCleanupResult | None:
        profile = await self._profile_repo.get_by_thread_id(channel_id)
        if profile is None:
            return None
        return await self._cleanup_profile(
            guild,
            profile,
            skip_profile_channel_id=channel_id,
            reason="profile channel deleted",
        )

    async def cleanup_by_thread_id(
        self,
        guild: discord.Guild,
        thread_id: int,
        *,
        parent_forum_id: int | None = None,
    ) -> ProfileCleanupResult | None:
        return await self.cleanup_by_profile_channel_id(guild, thread_id)

    async def cleanup_by_feed_channel_id(
        self,
        guild: discord.Guild,
        channel_id: int,
    ) -> ProfileCleanupResult | None:
        profile = await self._profile_repo.get_by_source_channel(channel_id)
        if profile is None:
            return None
        return await self._cleanup_profile(
            guild,
            profile,
            skip_feed_id=channel_id,
            reason="server feed deleted",
        )

    async def cleanup_by_profile_category_id(
        self,
        guild: discord.Guild,
        category_id: int,
    ) -> list[ProfileCleanupResult]:
        profiles = await self._profile_repo.list_by_profile_forum_channel(category_id)
        results: list[ProfileCleanupResult] = []
        for profile in profiles:
            result = await self._cleanup_profile(
                guild,
                profile,
                reason="profiles category deleted",
            )
            if result is not None:
                results.append(result)
        return results

    async def cleanup_by_profile_forum_id(
        self,
        guild: discord.Guild,
        forum_id: int,
    ) -> list[ProfileCleanupResult]:
        return await self.cleanup_by_profile_category_id(guild, forum_id)

    async def cleanup_by_network_id(
        self,
        guild: discord.Guild,
        network_id: int,
    ) -> list[ProfileCleanupResult]:
        profiles = await self._profile_repo.list_by_network_id(network_id)
        results: list[ProfileCleanupResult] = []
        for profile in profiles:
            result = await self._cleanup_profile(
                guild,
                profile,
                reason="network deleted",
            )
            if result is not None:
                results.append(result)
        return results

    async def cleanup_server(
        self,
        guild: discord.Guild,
        profile: ServerProfile,
    ) -> ProfileCleanupResult | None:
        return await self._cleanup_profile(
            guild,
            profile,
            reason="server deleted",
        )

    async def _cleanup_profile(
        self,
        guild: discord.Guild,
        profile: ServerProfile,
        *,
        reason: str,
        skip_feed_id: int | None = None,
        skip_profile_channel_id: int | None = None,
    ) -> ProfileCleanupResult | None:
        if profile.id in self._in_progress:
            logger.debug(
                "Profile cleanup already running",
                extra={"profile_id": profile.id, "reason": reason},
            )
            return None

        self._in_progress.add(profile.id)
        deleted_feed = False
        deleted_profile_channel = False
        deleted_role = False
        deleted_emoji = False
        deleted_record = False

        try:
            if profile.source_channel_id == profile.profile_thread_id:
                channel_id = profile.source_channel_id
                if channel_id != skip_feed_id and channel_id != skip_profile_channel_id:
                    deleted = await delete_channel(guild, channel_id, label="server feed")
                    deleted_feed = deleted
                    deleted_profile_channel = deleted
            else:
                if profile.source_channel_id != skip_feed_id:
                    deleted_feed = await delete_channel(
                        guild,
                        profile.source_channel_id,
                        label="server feed",
                    )

                if profile.profile_thread_id != skip_profile_channel_id:
                    deleted_profile_channel = await delete_channel(
                        guild,
                        profile.profile_thread_id,
                        label="server profile channel",
                    )

            if profile.partner_role_id is not None:
                deleted_role = await delete_role(
                    guild,
                    profile.partner_role_id,
                    label="server access",
                )

            if profile.emoji_id is not None:
                deleted_emoji = await self._delete_emoji(guild, profile.emoji_id)

            await self._relay_records.delete_by_profile_id(profile.id)

            removed = await self._profile_repo.delete_by_thread_id(profile.profile_thread_id)
            deleted_record = removed is not None
            if deleted_record:
                await self._profile_cache.load_cache()

            logger.info(
                "Server profile cleaned up",
                extra={
                    "profile_id": profile.id,
                    "server_name": profile.server_name,
                    "reason": reason,
                    "deleted_feed": deleted_feed,
                    "deleted_profile_channel": deleted_profile_channel,
                    "deleted_role": deleted_role,
                    "deleted_emoji": deleted_emoji,
                },
            )
            return ProfileCleanupResult(
                profile=profile,
                deleted_feed=deleted_feed,
                deleted_profile_channel=deleted_profile_channel,
                deleted_role=deleted_role,
                deleted_emoji=deleted_emoji,
                deleted_record=deleted_record,
            )
        finally:
            self._in_progress.discard(profile.id)

    async def _delete_emoji(self, guild: discord.Guild, emoji_id: int) -> bool:
        try:
            await self._emoji_service.delete_emoji(guild, emoji_id)
            return True
        except discord.HTTPException as exc:
            logger.warning(
                "Could not delete profile emoji during cleanup",
                extra={"emoji_id": emoji_id, "error": str(exc)},
            )
            return False
