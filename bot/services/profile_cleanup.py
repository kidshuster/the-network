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
    deleted_forum: bool
    deleted_role: bool
    deleted_emoji: bool
    deleted_record: bool


class ProfileCleanupService:
    """Remove partner feed, profile forum, role, emoji, and DB row together."""

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

    async def cleanup_by_thread_id(
        self,
        guild: discord.Guild,
        thread_id: int,
        *,
        parent_forum_id: int | None = None,
    ) -> ProfileCleanupResult | None:
        profile = await self._profile_repo.get_by_thread_id(thread_id)
        if profile is None:
            return None
        forum_id = profile.profile_forum_channel_id or parent_forum_id
        return await self._cleanup_profile(
            guild,
            profile,
            skip_thread_id=thread_id,
            forum_id=forum_id,
            reason="profile thread deleted",
        )

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
            reason="partner feed deleted",
        )

    async def cleanup_by_profile_forum_id(
        self,
        guild: discord.Guild,
        forum_id: int,
    ) -> list[ProfileCleanupResult]:
        profiles = await self._profile_repo.list_by_profile_forum_channel(forum_id)
        results: list[ProfileCleanupResult] = []
        for profile in profiles:
            result = await self._cleanup_profile(
                guild,
                profile,
                skip_forum_id=forum_id,
                reason="partner profile forum deleted",
            )
            if result is not None:
                results.append(result)
        return results

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
        skip_forum_id: int | None = None,
        skip_thread_id: int | None = None,
        forum_id: int | None = None,
    ) -> ProfileCleanupResult | None:
        if profile.id in self._in_progress:
            logger.debug(
                "Profile cleanup already running",
                extra={"profile_id": profile.id, "reason": reason},
            )
            return None

        self._in_progress.add(profile.id)
        deleted_feed = False
        deleted_forum = False
        deleted_role = False
        deleted_emoji = False
        deleted_record = False

        try:
            resolved_forum_id = forum_id or profile.profile_forum_channel_id

            if (
                profile.source_channel_id != skip_feed_id
                and profile.source_channel_id != skip_forum_id
            ):
                deleted_feed = await delete_channel(
                    guild,
                    profile.source_channel_id,
                    label="partner feed",
                )

            if await self._should_delete_partner_forum(
                profile,
                resolved_forum_id,
                skip_forum_id,
            ):
                assert resolved_forum_id is not None
                deleted_forum = await delete_channel(
                    guild,
                    resolved_forum_id,
                    label="partner profile forum",
                )
            elif skip_thread_id != profile.profile_thread_id:
                await self._delete_thread(guild, profile.profile_thread_id)

            if profile.partner_role_id is not None:
                deleted_role = await delete_role(
                    guild,
                    profile.partner_role_id,
                    label="partner profile",
                )

            if profile.emoji_id is not None:
                deleted_emoji = await self._delete_emoji(guild, profile.emoji_id)

            await self._relay_records.delete_by_profile_id(profile.id)

            removed = await self._profile_repo.delete_by_thread_id(profile.profile_thread_id)
            deleted_record = removed is not None
            if deleted_record:
                await self._profile_cache.load_cache()

            logger.info(
                "Partner profile cleaned up",
                extra={
                    "profile_id": profile.id,
                    "server_name": profile.server_name,
                    "reason": reason,
                    "deleted_feed": deleted_feed,
                    "deleted_forum": deleted_forum,
                    "deleted_role": deleted_role,
                    "deleted_emoji": deleted_emoji,
                },
            )
            return ProfileCleanupResult(
                profile=profile,
                deleted_feed=deleted_feed,
                deleted_forum=deleted_forum,
                deleted_role=deleted_role,
                deleted_emoji=deleted_emoji,
                deleted_record=deleted_record,
            )
        finally:
            self._in_progress.discard(profile.id)

    async def _should_delete_partner_forum(
        self,
        profile: ServerProfile,
        forum_id: int | None,
        skip_forum_id: int | None,
    ) -> bool:
        if forum_id is None or forum_id == skip_forum_id:
            return False
        if profile.profile_forum_channel_id is None:
            return False
        if profile.profile_forum_channel_id != forum_id:
            return False
        network = await self._network_repo.get_by_id(profile.network_id)
        if network is not None and network.profile_forum_channel_id == forum_id:
            return False
        return True

    async def _delete_thread(self, guild: discord.Guild, thread_id: int) -> bool:
        thread = guild.get_thread(thread_id)
        if thread is None:
            try:
                fetched = await guild.fetch_channel(thread_id)
            except discord.NotFound:
                return False
            except discord.HTTPException as exc:
                logger.warning(
                    "Could not fetch thread for cleanup",
                    extra={"thread_id": thread_id, "error": str(exc)},
                )
                return False
            if not isinstance(fetched, discord.Thread):
                return False
            thread = fetched

        try:
            await thread.delete(reason="The Network: partner profile cleanup")
            return True
        except discord.NotFound:
            return False
        except discord.HTTPException as exc:
            logger.warning(
                "Could not delete thread during profile cleanup",
                extra={"thread_id": thread_id, "error": str(exc)},
            )
            return False

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
