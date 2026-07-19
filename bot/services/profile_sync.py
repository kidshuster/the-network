from __future__ import annotations

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
from bot.services.profile_provision import ProfileProvisionService, ServerProvisionResult
from bot.services.routing_service import RoutingService

logger = logging.getLogger(__name__)

_ALLOWED_SOURCE_TYPES = {
    discord.ChannelType.text,
    discord.ChannelType.news,
}


async def _pin_profile_starter(message: discord.Message) -> None:
    """Legacy no-op — profile cards bump to the channel bottom instead of pinning."""
    return


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
class PartnerProfileUpdateResult:
    success: bool
    profile: ServerProfile | None = None
    error: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreateProfileResult:
    success: bool
    feed_channel: discord.TextChannel | None = None
    profile: ServerProfile | None = None
    sync_result: SyncResult | None = None
    error: str | None = None
    server_role: discord.Role | None = None
    starter_message: discord.Message | None = None

    @property
    def profile_channel(self) -> discord.TextChannel | None:
        """Legacy alias — profile lives in the feed channel now."""
        return self.feed_channel


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
        network_key: str,
        display_name: str | None = None,
        enabled: bool = True,
        profile_image: discord.Attachment | None = None,
        profile_image_bytes: bytes | None = None,
        starter_view: discord.ui.View | None = None,
    ) -> CreateProfileResult:
        from bot.services.image_service import normalize_image_bytes
        from bot.services.profile_post import build_profile_embed

        provision: ServerProvisionResult | None = None
        try:
            name = server_name.strip()
            if not name:
                raise ProfileValidationError("Server name cannot be empty.")

            label = (display_name or name).strip()
            normalized_key = network_key.strip().lower()
            network = await self._network_repo.get_by_key(normalized_key)
            if network is None:
                raise ProfileValidationError(f"Network '{normalized_key}' was not found.")

            existing_server = await self._profile_repo.get_by_network_and_server_name(
                network.id,
                name,
            )
            if existing_server is not None:
                raise ProfileValidationError(
                    f"A server named {name!r} already exists on network `{network.key}`."
                )

            if profile_image is None and profile_image_bytes is None:
                raise ProfileValidationError("A profile image is required.")

            provision = await self._profile_provision.provision_server(
                guild,
                bot_member,
                network_key=network.key,
                server_name=name,
                feed_category_id=network.feed_category_id,
                admin_role_name=self._settings.network_access_role_name,
            )

            feed_channel = provision.feed_channel
            parsed = ParsedProfile(
                server_name=name,
                source_channel_id=feed_channel.id,
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

            if profile_image_bytes is not None:
                raw_image = profile_image_bytes
            else:
                assert profile_image is not None
                raw_image = await profile_image.read()
            normalized_image = normalize_image_bytes(raw_image)

            embed = build_profile_embed(
                server_name=parsed.server_name,
                display_name=parsed.display_name,
                source_channel_id=parsed.source_channel_id,
                network_key=network.key,
                enabled=parsed.enabled,
            )
            starter = await feed_channel.send(
                embed=embed,
                view=starter_view,
            )
            await _pin_profile_starter(starter)
            sync_result = await self.sync_profile(
                guild,
                feed_channel,
                starter_message=starter,
                profile_image=normalized_image,
                partner_role_id=provision.server_role.id,
                profile_category_id=network.feed_category_id,
            )
            if not sync_result.success:
                return CreateProfileResult(
                    success=False,
                    feed_channel=feed_channel,
                    sync_result=sync_result,
                    error=sync_result.error,
                    server_role=provision.server_role,
                    starter_message=starter,
                )
            if sync_result.profile is not None:
                from bot.services.profile_sticky import refresh_profile_starter_embed

                try:
                    await refresh_profile_starter_embed(
                        starter,
                        sync_result.profile,
                        network_key=network.key,
                        view=starter_view,
                    )
                except discord.HTTPException:
                    pass
            return CreateProfileResult(
                success=True,
                feed_channel=feed_channel,
                profile=sync_result.profile,
                sync_result=sync_result,
                server_role=provision.server_role,
                starter_message=starter,
            )
        except (ProfileParseError, ProfileValidationError) as exc:
            return CreateProfileResult(success=False, error=str(exc))
        except discord.HTTPException as exc:
            return CreateProfileResult(success=False, error=f"Discord API error: {exc}")

    async def sync_all_profiles(
        self,
        guild: discord.Guild,
        feed_category_id: int,
    ) -> SyncAllResult:
        synced = 0
        failed = 0
        preserved = 0
        seen_channel_ids: set[int] = set()

        for channel in guild.text_channels:
            if channel.category_id != feed_category_id:
                continue
            if channel.id in seen_channel_ids:
                continue
            seen_channel_ids.add(channel.id)
            result = await self.sync_profile(guild, channel)
            if result.success:
                synced += 1
            else:
                failed += 1
                if result.preserved_existing:
                    preserved += 1

        removed_profiles = await self._prune_orphaned_profiles(seen_channel_ids)
        if removed_profiles:
            await self._profile_cache.load_cache()

        return SyncAllResult(
            synced=synced,
            failed=failed,
            preserved=preserved,
            removed=len(removed_profiles),
            removed_names=tuple(profile.server_name for profile in removed_profiles),
        )

    async def sync_all_forum(
        self,
        guild: discord.Guild,
        forum: discord.ForumChannel,
    ) -> SyncAllResult:
        """Legacy forum sync — kept for archived forum threads."""
        synced = 0
        failed = 0
        preserved = 0
        seen_channel_ids: set[int] = set()

        async def sync_one(thread: discord.Thread) -> None:
            nonlocal synced, failed, preserved
            if thread.id in seen_channel_ids:
                return
            seen_channel_ids.add(thread.id)
            result = await self.sync_profile(guild, thread)
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

        removed_profiles = await self._prune_orphaned_profiles(seen_channel_ids)
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
        **kwargs: object,
    ) -> SyncResult:
        return await self.sync_profile(guild, thread, **kwargs)  # type: ignore[arg-type]

    async def sync_profile(
        self,
        guild: discord.Guild,
        profile_channel: discord.TextChannel | discord.Thread,
        *,
        force_emoji: bool = False,
        starter_message: discord.Message | None = None,
        profile_image: ProfileImage | None = None,
        partner_role_id: int | None = None,
        profile_category_id: int | None = None,
        profile_forum_channel_id: int | None = None,
    ) -> SyncResult:
        category_id = profile_category_id or profile_forum_channel_id
        existing = await self._profile_repo.get_by_thread_id(profile_channel.id)
        channel_name = getattr(profile_channel, "name", "")
        try:
            starter = starter_message or await self._fetch_starter_message(profile_channel)
            if profile_image is None and not starter.attachments:
                starter = await self._fetch_starter_message(profile_channel)
            parsed = parse_starter_message(starter, thread_name=channel_name)
            network = await self._resolve_network(guild, parsed)
            await self._validate_source_channel(guild, parsed.source_channel_id, network)

            resolved_category_id = category_id
            if resolved_category_id is None:
                parent_id = getattr(profile_channel, "category_id", None) or getattr(
                    profile_channel, "parent_id", None
                )
                if isinstance(parent_id, int):
                    resolved_category_id = parent_id
            if resolved_category_id is None and existing is not None:
                resolved_category_id = existing.profile_forum_channel_id

            previous_hash = existing.image_hash if existing else None
            previous_emoji_id = existing.emoji_id if existing else None

            profile = await self._profile_repo.upsert(
                guild_id=guild.id,
                profile_thread_id=profile_channel.id,
                profile_starter_message_id=starter.id,
                source_channel_id=parsed.source_channel_id,
                network_id=network.id,
                server_name=parsed.server_name,
                display_name=parsed.display_name,
                enabled=parsed.enabled,
                partner_role_id=partner_role_id
                if partner_role_id is not None
                else (existing.partner_role_id if existing else None),
                profile_forum_channel_id=resolved_category_id,
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

            try:
                from bot.services.profile_sticky import refresh_profile_starter_embed

                await refresh_profile_starter_embed(
                    starter,
                    profile,
                    network_key=network.key,
                )
            except discord.HTTPException:
                warnings.append("Could not refresh profile card embed.")

            await self._profile_cache.load_cache()
            logger.info(
                "Profile synced",
                extra={
                    "profile_channel_id": profile_channel.id,
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
                    extra={"profile_channel_id": profile_channel.id, "error": str(exc)},
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
                    extra={"profile_channel_id": profile_channel.id, "error": str(exc)},
                )
                return SyncResult(
                    success=False,
                    error=str(exc),
                    preserved_existing=True,
                    profile=existing,
                )
            return SyncResult(success=False, error=str(exc))

    async def update_partner_profile(
        self,
        guild: discord.Guild,
        profile_channel: discord.TextChannel,
        *,
        display_name: str | None = None,
        profile_image: discord.Attachment | None = None,
        profile_image_bytes: bytes | None = None,
        starter_view: discord.ui.View | None = None,
    ) -> PartnerProfileUpdateResult:
        from bot.services.image_service import normalize_image_bytes
        from bot.services.profile_sticky import (
            refresh_profile_starter_embed,
            repost_profile_sticky_after_edit,
        )

        profile = await self._profile_repo.get_by_thread_id(profile_channel.id)
        if profile is None:
            return PartnerProfileUpdateResult(
                success=False,
                error="This channel is not a registered server feed.",
            )

        if display_name is None and profile_image is None and profile_image_bytes is None:
            return PartnerProfileUpdateResult(
                success=False,
                error="Provide a display name and/or profile image to update.",
            )

        new_display = profile.display_name
        if display_name is not None:
            cleaned = display_name.strip()
            if not cleaned:
                return PartnerProfileUpdateResult(
                    success=False,
                    error="Display name cannot be empty.",
                )
            new_display = cleaned

        normalized_image = None
        raw_image: bytes | None = profile_image_bytes
        if profile_image is not None:
            try:
                raw_image = await profile_image.read()
            except discord.HTTPException:
                return PartnerProfileUpdateResult(
                    success=False,
                    error="Failed to read profile image attachment.",
                )
        if raw_image is not None:
            try:
                normalized_image = normalize_image_bytes(raw_image)
            except ProfileValidationError as exc:
                return PartnerProfileUpdateResult(success=False, error=str(exc))

        try:
            network = await self._network_repo.get_by_id(profile.network_id)
            network_key = network.key if network is not None else None
            if starter_view is None:
                return PartnerProfileUpdateResult(
                    success=False,
                    error="Profile update view is not configured.",
                )

            new_starter = await repost_profile_sticky_after_edit(
                profile_channel,
                profile,
                display_name=new_display,
                enabled=profile.enabled,
                network_key=network_key,
                edit_view_factory=lambda _channel_id: starter_view,
            )
            if new_starter is None:
                return PartnerProfileUpdateResult(
                    success=False,
                    error="Failed to refresh the profile card in this channel.",
                )

            profile = await self._profile_repo.update_display_name(profile_channel.id, new_display)
            profile = await self._profile_repo.update_starter_message_id(
                profile_channel.id,
                new_starter.id,
            )

            warnings: list[str] = []
            if normalized_image is not None:
                profile, emoji_warnings = await self._sync_emoji(
                    guild,
                    profile,
                    new_starter,
                    previous_hash=profile.image_hash,
                    previous_emoji_id=profile.emoji_id,
                    force=True,
                    profile_image=normalized_image,
                )
                warnings.extend(emoji_warnings)
            elif display_name is not None:
                profile, emoji_warnings = await self._sync_emoji(
                    guild,
                    profile,
                    new_starter,
                    previous_hash=profile.image_hash,
                    previous_emoji_id=profile.emoji_id,
                    force=False,
                )
                warnings.extend(emoji_warnings)

            try:
                await refresh_profile_starter_embed(
                    new_starter,
                    profile,
                    network_key=network_key,
                    view=starter_view,
                )
            except discord.HTTPException:
                pass

            await self._profile_cache.load_cache()
            return PartnerProfileUpdateResult(
                success=True,
                profile=profile,
                warnings=tuple(warnings),
            )
        except ProfileValidationError as exc:
            return PartnerProfileUpdateResult(success=False, error=str(exc))
        except discord.HTTPException as exc:
            return PartnerProfileUpdateResult(success=False, error=f"Discord API error: {exc}")

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

    async def _fetch_starter_message(
        self,
        profile_channel: discord.TextChannel | discord.Thread,
    ) -> discord.Message:
        if isinstance(profile_channel, discord.Thread):
            try:
                return await profile_channel.fetch_message(profile_channel.id)
            except discord.HTTPException:
                pass
        async for message in profile_channel.history(limit=1, oldest_first=True):
            return message
        raise ProfileValidationError("Profile channel has no starter message.")

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

        if network.profile_forum_channel_id is not None:
            channel = guild.get_channel(source_channel_id)
            if channel is None:
                fetched = await guild.fetch_channel(source_channel_id)
                channel = fetched if isinstance(fetched, discord.abc.GuildChannel) else None
            parent_id = getattr(channel, "category_id", None)
            if parent_id == network.profile_forum_channel_id:
                raise ProfileValidationError(
                    "Source channel cannot be in the network profiles category."
                )
            if source_channel_id == network.profile_forum_channel_id:
                raise ProfileValidationError(
                    "Source channel cannot be the network profiles category."
                )
