from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import discord

from bot.config import Settings
from bot.db.repositories import NetworkRepository, ProfileRepository
from bot.domain.errors import EmojiSyncError, ProfileParseError, ProfileValidationError
from bot.domain.network import Network
from bot.domain.profile import ServerProfile
from bot.domain.profile_image import ProfileImage
from bot.services.emoji_service import EmojiService
from bot.services.image_service import extract_profile_image
from bot.services.profile_cache import ProfileCache
from bot.services.profile_parser import ParsedProfile
from bot.services.profile_post import parse_starter_message
from bot.services.profile_provision import PartnerProvisionResult, ProfileProvisionService
from bot.services.routing_service import RoutingService

logger = logging.getLogger(__name__)

_ALLOWED_SOURCE_TYPES = {
    discord.ChannelType.text,
    discord.ChannelType.news,
}


@dataclass(frozen=True)
class SyncResult:
    success: bool
    profile: ServerProfile | None = None
    error: str | None = None
    warnings: tuple[str, ...] = ()
    preserved_existing: bool = False


@dataclass(frozen=True)
class SyncAllResult:
    synced: int
    failed: int
    preserved: int
    removed: int
    removed_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreateProfileResult:
    success: bool
    thread: discord.Thread | None = None
    profile: ServerProfile | None = None
    sync_result: SyncResult | None = None
    error: str | None = None
    feed_channel: discord.TextChannel | None = None
    profile_forum: discord.ForumChannel | None = None
    partner_role: discord.Role | None = None


class ProfileSyncService:
    def __init__(
        self,
        profile_repo: ProfileRepository,
        network_repo: NetworkRepository,
        routing_service: RoutingService,
        profile_cache: ProfileCache,
        emoji_service: EmojiService,
        settings: Settings,
    ) -> None:
        self._profile_repo = profile_repo
        self._network_repo = network_repo
        self._routing_service = routing_service
        self._profile_cache = profile_cache
        self._emoji_service = emoji_service
        self._settings = settings
        self._profile_provision = ProfileProvisionService()

    async def create_profile(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        server_name: str,
        profile_image: discord.Attachment,
        network_key: str,
        display_name: str | None = None,
        enabled: bool = True,
    ) -> CreateProfileResult:
        from bot.services.image_service import normalize_image_bytes
        from bot.services.profile_post import build_profile_embed

        partner: PartnerProvisionResult | None = None
        try:
            name = server_name.strip()
            if not name:
                raise ProfileValidationError("Server name cannot be empty.")

            label = (display_name or name).strip()
            normalized_key = network_key.strip().lower()
            network = await self._network_repo.get_by_key(normalized_key)
            if network is None:
                raise ProfileValidationError(f"Network '{normalized_key}' was not found.")
            if network.profile_forum_channel_id is None:
                raise ProfileValidationError(
                    f"Network `{network.key}` has no profiles forum. Run `/network create` first."
                )

            partner = await self._profile_provision.provision_partner(
                guild,
                bot_member,
                network_key=network.key,
                server_name=name,
                feed_category_id=network.feed_category_id,
                profile_forum_channel_id=network.profile_forum_channel_id,
                admin_role_name=self._settings.network_access_role_name,
            )

            parsed = ParsedProfile(
                server_name=name,
                source_channel_id=partner.feed_channel.id,
                enabled=enabled,
                network_key=network.key,
                display_name=label,
            )
            await self._validate_source_channel(guild, parsed.source_channel_id, network)

            existing = await self._profile_repo.get_by_source_channel(parsed.source_channel_id)
            if existing is not None:
                raise ProfileValidationError(
                    f"Source channel <#{parsed.source_channel_id}> is already used by "
                    f"'{existing.server_name}'."
                )

            raw_image = await profile_image.read()
            normalized_image = normalize_image_bytes(raw_image)

            embed = build_profile_embed(
                server_name=parsed.server_name,
                display_name=parsed.display_name,
                source_channel_id=parsed.source_channel_id,
                network_key=network.key,
                enabled=parsed.enabled,
            )
            thread_with_message = await partner.profile_forum.create_thread(
                name=parsed.server_name[:100],
                embed=embed,
                file=discord.File(fp=io.BytesIO(raw_image), filename="profile.png"),
                content="\u200b",
            )
            thread = thread_with_message.thread
            starter = thread_with_message.message
            sync_result = await self.sync_thread(
                guild,
                thread,
                starter_message=starter,
                profile_image=normalized_image,
                partner_role_id=partner.partner_role.id,
                profile_forum_channel_id=network.profile_forum_channel_id,
            )
            if not sync_result.success:
                return CreateProfileResult(
                    success=False,
                    thread=thread,
                    sync_result=sync_result,
                    error=sync_result.error,
                    feed_channel=partner.feed_channel,
                    profile_forum=partner.profile_forum,
                    partner_role=partner.partner_role,
                )
            return CreateProfileResult(
                success=True,
                thread=thread,
                profile=sync_result.profile,
                sync_result=sync_result,
                feed_channel=partner.feed_channel,
                profile_forum=partner.profile_forum,
                partner_role=partner.partner_role,
            )
        except (ProfileParseError, ProfileValidationError) as exc:
            return CreateProfileResult(success=False, error=str(exc))
        except discord.HTTPException as exc:
            return CreateProfileResult(success=False, error=f"Discord API error: {exc}")

    async def sync_all_forum(
        self,
        guild: discord.Guild,
        forum: discord.ForumChannel,
    ) -> SyncAllResult:
        synced = 0
        failed = 0
        preserved = 0
        seen_thread_ids: set[int] = set()

        async def sync_one(thread: discord.Thread) -> None:
            nonlocal synced, failed, preserved
            if thread.id in seen_thread_ids:
                return
            seen_thread_ids.add(thread.id)
            result = await self.sync_thread(guild, thread)
            if result.success:
                synced += 1
            else:
                failed += 1
                if result.preserved_existing:
                    preserved += 1

        for thread in guild.threads:
            if thread.parent_id == forum.id:
                await sync_one(thread)
        async for thread in forum.archived_threads(limit=None):
            await sync_one(thread)

        removed_profiles = await self._prune_orphaned_profiles(seen_thread_ids)
        if removed_profiles:
            await self._profile_cache.load_cache()

        return SyncAllResult(
            synced=synced,
            failed=failed,
            preserved=preserved,
            removed=len(removed_profiles),
            removed_names=tuple(profile.server_name for profile in removed_profiles),
        )

    async def _prune_orphaned_profiles(
        self,
        present_thread_ids: set[int],
    ) -> list[ServerProfile]:
        removed: list[ServerProfile] = []
        for profile in await self._profile_repo.list_all():
            if profile.profile_thread_id in present_thread_ids:
                continue
            deleted = await self._profile_repo.delete_by_thread_id(profile.profile_thread_id)
            if deleted is not None:
                removed.append(deleted)
                logger.info(
                    "Removed orphaned profile",
                    extra={
                        "profile_thread_id": deleted.profile_thread_id,
                        "server_name": deleted.server_name,
                    },
                )
        return removed

    async def sync_thread(
        self,
        guild: discord.Guild,
        thread: discord.Thread,
        *,
        force_emoji: bool = False,
        starter_message: discord.Message | None = None,
        profile_image: ProfileImage | None = None,
        partner_role_id: int | None = None,
        profile_forum_channel_id: int | None = None,
    ) -> SyncResult:
        existing = await self._profile_repo.get_by_thread_id(thread.id)
        try:
            starter = starter_message or await self._fetch_starter_message(thread)
            if profile_image is None and not starter.attachments:
                starter = await self._fetch_starter_message(thread)
            parsed = parse_starter_message(starter, thread_name=thread.name)
            network = await self._resolve_network(guild, parsed)
            await self._validate_source_channel(guild, parsed.source_channel_id, network)

            forum_id = profile_forum_channel_id
            if forum_id is None:
                parent_id = getattr(thread, "parent_id", None)
                if isinstance(parent_id, int):
                    forum_id = parent_id
            if forum_id is None and existing is not None:
                forum_id = existing.profile_forum_channel_id

            previous_hash = existing.image_hash if existing else None
            previous_emoji_id = existing.emoji_id if existing else None

            profile = await self._profile_repo.upsert(
                guild_id=guild.id,
                profile_thread_id=thread.id,
                profile_starter_message_id=starter.id,
                source_channel_id=parsed.source_channel_id,
                network_id=network.id,
                server_name=parsed.server_name,
                display_name=parsed.display_name,
                enabled=parsed.enabled,
                partner_role_id=partner_role_id
                if partner_role_id is not None
                else (existing.partner_role_id if existing else None),
                profile_forum_channel_id=forum_id,
            )

            warnings: list[str] = []
            profile, emoji_warnings = await self._sync_emoji(
                guild,
                profile,
                starter,
                previous_hash=previous_hash,
                previous_emoji_id=previous_emoji_id,
                force=force_emoji,
                profile_image=profile_image,
            )
            warnings.extend(emoji_warnings)

            await self._profile_cache.load_cache()
            logger.info(
                "Profile synced",
                extra={
                    "profile_thread_id": thread.id,
                    "source_channel_id": profile.source_channel_id,
                    "network_id": network.id,
                    "emoji_id": profile.emoji_id,
                },
            )
            return SyncResult(success=True, profile=profile, warnings=tuple(warnings))
        except ProfileParseError as exc:
            if existing is not None:
                logger.warning(
                    "Profile parse failed; preserved existing record",
                    extra={"profile_thread_id": thread.id, "error": str(exc)},
                )
                return SyncResult(
                    success=False,
                    error=str(exc),
                    preserved_existing=True,
                    profile=existing,
                )
            return SyncResult(success=False, error=str(exc))
        except ProfileValidationError as exc:
            if existing is not None:
                logger.warning(
                    "Profile validation failed; preserved existing record",
                    extra={"profile_thread_id": thread.id, "error": str(exc)},
                )
                return SyncResult(
                    success=False,
                    error=str(exc),
                    preserved_existing=True,
                    profile=existing,
                )
            return SyncResult(success=False, error=str(exc))

    async def _sync_emoji(
        self,
        guild: discord.Guild,
        profile: ServerProfile,
        starter: discord.Message,
        *,
        previous_hash: str | None,
        previous_emoji_id: int | None,
        force: bool,
        profile_image: ProfileImage | None = None,
    ) -> tuple[ServerProfile, list[str]]:
        warnings: list[str] = []
        image: ProfileImage | None
        try:
            if profile_image is not None:
                image = profile_image
            else:
                image = await extract_profile_image(starter)
        except ProfileValidationError as exc:
            if force:
                raise
            warnings.append(str(exc))
            return profile, warnings

        if image is None:
            if force:
                raise ProfileValidationError(
                    "Profile thread starter message has no supported image attachment."
                )
            warnings.append("No profile image attachment found; emoji was not updated.")
            return profile, warnings

        try:
            emoji_result = await self._emoji_service.sync_for_profile(
                guild,
                profile,
                image,
                previous_hash=previous_hash,
                previous_emoji_id=previous_emoji_id,
                force=force,
            )
        except EmojiSyncError as exc:
            warnings.append(str(exc))
            return profile, warnings

        if emoji_result.skipped:
            return profile, warnings

        if emoji_result.recreated and emoji_result.emoji_id is not None:
            warnings.append("Custom emoji created or updated.")

        profile = await self._profile_repo.update_emoji_fields(
            profile.profile_thread_id,
            emoji_id=emoji_result.emoji_id,
            emoji_name=emoji_result.emoji_name,
            image_hash=emoji_result.image_hash,
            degraded_reason=emoji_result.degraded_reason,
        )
        if emoji_result.delete_emoji_id is not None:
            await self._emoji_service.delete_emoji(guild, emoji_result.delete_emoji_id)
        if emoji_result.warning:
            warnings.append(emoji_result.warning)
        return profile, warnings

    async def _fetch_starter_message(self, thread: discord.Thread) -> discord.Message:
        try:
            return await thread.fetch_message(thread.id)
        except discord.HTTPException:
            async for message in thread.history(limit=1, oldest_first=True):
                return message
        raise ProfileValidationError("Forum thread has no starter message.")

    async def _resolve_network(
        self,
        guild: discord.Guild,
        parsed: ParsedProfile,
    ) -> Network:
        channel = guild.get_channel(parsed.source_channel_id)
        if channel is None:
            fetched = await guild.fetch_channel(parsed.source_channel_id)
            if not isinstance(fetched, discord.abc.GuildChannel):
                raise ProfileValidationError(
                    f"Source channel <#{parsed.source_channel_id}> was not found."
                )
            channel = fetched

        parent_id = getattr(channel, "category_id", None)
        if parent_id is None:
            raise ProfileValidationError(
                "Source channel must be inside a configured feed category."
            )

        inferred = self._routing_service.get_by_category(parent_id)
        if parsed.network_key:
            explicit = await self._network_repo.get_by_key(parsed.network_key)
            if explicit is None:
                raise ProfileValidationError(f"Network '{parsed.network_key}' was not found.")
            if explicit.feed_category_id != parent_id:
                raise ProfileValidationError(
                    f"Network '{parsed.network_key}' uses feed category "
                    f"<#{explicit.feed_category_id}>, but source channel is in "
                    f"<#{parent_id}>."
                )
            return explicit

        if inferred is None:
            raise ProfileValidationError(
                "Could not infer network from source channel category. "
                "Register the category with `/network create`."
            )
        return inferred

    async def _validate_source_channel(
        self,
        guild: discord.Guild,
        source_channel_id: int,
        network: Network,
    ) -> None:
        if guild.id != self._settings.guild_id:
            raise ProfileValidationError("Profile sync only runs in the configured central guild.")

        channel = guild.get_channel(source_channel_id)
        if channel is None:
            fetched = await guild.fetch_channel(source_channel_id)
            if not isinstance(fetched, discord.abc.GuildChannel):
                raise ProfileValidationError("Source channel must be a guild channel.")
            channel = fetched

        channel_type = getattr(channel, "type", None)
        if channel_type not in _ALLOWED_SOURCE_TYPES:
            raise ProfileValidationError("Source channel must be a text or announcement channel.")

        parent_id = getattr(channel, "category_id", None)
        if parent_id != network.feed_category_id:
            raise ProfileValidationError(
                "Source channel must be inside network feed category "
                f"<#{network.feed_category_id}>."
            )

        if source_channel_id == network.output_channel_id:
            raise ProfileValidationError("Source channel cannot be the network output channel.")

        if network.concat_channel_id is not None and source_channel_id == network.concat_channel_id:
            raise ProfileValidationError("Source channel cannot be the network concat channel.")

        if (
            network.profile_forum_channel_id is not None
            and source_channel_id == network.profile_forum_channel_id
        ):
            raise ProfileValidationError("Source channel cannot be the network profile forum.")
