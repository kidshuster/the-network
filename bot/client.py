from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot.context import BotContext
from bot.db import migrations
from bot.db.connection import Database
from bot.db.repositories import (
    NetworkRepository,
    ProfileRepository,
    RelayRecordRepository,
    ServerRequestRepository,
    SettingsRepository,
)
from bot.services.bot_settings import BotSettingsService
from bot.services.emoji_service import EmojiService
from bot.services.network_cleanup import NetworkCleanupService
from bot.services.profile_cache import ProfileCache
from bot.services.profile_cleanup import ProfileCleanupService
from bot.services.profile_sync import ProfileSyncService
from bot.services.relay_service import RelayService
from bot.services.routing_service import RoutingService
from bot.services.topgg import TopggService

if TYPE_CHECKING:
    from bot.config import Settings

logger = logging.getLogger(__name__)


class NetworkRelayBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.message_content = True
        intents.members = True

        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.db = Database(settings.database_path)
        self.bot_context: BotContext | None = None
        self.schema_version: int = 0
        self._topgg: TopggService | None = None

    async def setup_hook(self) -> None:
        await self.db.connect()
        self.schema_version = await migrations.run_migrations(self.db)

        network_repo = NetworkRepository(self.db)
        profile_repo = ProfileRepository(self.db)
        relay_record_repo = RelayRecordRepository(self.db)
        routing_service = RoutingService(network_repo)
        await routing_service.load_cache()

        profile_cache = ProfileCache(profile_repo)
        await profile_cache.load_cache()

        emoji_service = EmojiService()
        profile_sync = ProfileSyncService(
            profile_repo,
            network_repo,
            routing_service,
            profile_cache,
            emoji_service,
            self.settings,
        )
        profile_cleanup = ProfileCleanupService(
            profile_repo,
            network_repo,
            profile_cache,
            emoji_service,
            relay_record_repo,
        )
        network_cleanup = NetworkCleanupService(profile_cleanup, profile_cache)

        settings_repo = SettingsRepository(self.db)
        server_request_repo = ServerRequestRepository(self.db)
        bot_settings = BotSettingsService(settings_repo, self.settings)
        await bot_settings.load()

        relay_service = RelayService(
            self.settings,
            routing_service,
            profile_cache,
            relay_record_repo,
        )

        self.bot_context = BotContext.create(
            self.settings,
            self.db,
            network_repo,
            profile_repo,
            relay_record_repo,
            routing_service,
            profile_cache,
            profile_sync,
            profile_cleanup,
            network_cleanup,
            relay_service,
            bot_settings,
            settings_repo,
            server_request_repo,
        )
        self.bot_context.network_count = routing_service.network_count
        self.bot_context.profile_count = profile_cache.profile_count
        self.bot_context.enabled_profile_count = profile_cache.enabled_profile_count

        await self.load_extension("bot.cogs.network")
        await self.load_extension("bot.cogs.servers")
        await self.load_extension("bot.cogs.relay")

        await self._register_persistent_views()

        guild = discord.Object(id=self.settings.guild_id)
        self.tree.copy_global_to(guild=guild)
        try:
            synced = await self.tree.sync(guild=guild)
            logger.info(
                "Slash commands synced to guild",
                extra={"guild_id": self.settings.guild_id, "command_count": len(synced)},
            )
        except discord.Forbidden:
            logger.warning(
                "Could not sync slash commands — bot may not be in the guild or lacks "
                "applications.commands scope. Re-invite the bot, then restart.",
                extra={"guild_id": self.settings.guild_id},
            )
        except discord.HTTPException as exc:
            logger.warning(
                "Slash command sync failed",
                extra={"guild_id": self.settings.guild_id, "error": str(exc)},
            )

    async def on_ready(self) -> None:
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            logger.error(
                "Configured guild not visible to bot",
                extra={"guild_id": self.settings.guild_id},
            )
            return

        context = self.bot_context
        logger.info(
            "Bot ready",
            extra={
                "guild_id": guild.id,
                "guild_name": guild.name,
                "user": str(self.user),
                "schema_version": self.schema_version,
                "network_count": context.network_count if context else 0,
                "profile_count": context.profile_count if context else 0,
                "latency_ms": round(self.latency * 1000),
            },
        )

        if self.settings.topgg_token and self._topgg is None:
            self._topgg = TopggService(self, self.settings.topgg_token)
            await self._topgg.start()

        asyncio.create_task(self._sync_profile_stickies_on_startup(guild))

    async def _sync_profile_stickies_on_startup(self, guild: discord.Guild) -> None:
        context = self.bot_context
        if context is None:
            return

        from bot.services.profile_sticky import sync_all_profile_stickies
        from bot.ui.profile_views import EditProfileView

        async def resolve_network_key(network_id: int) -> str | None:
            network = await context.network_repo.get_by_id(network_id)
            return network.key if network is not None else None

        async def update_starter_message_id(thread_id: int, message_id: int) -> None:
            await context.profile_repo.update_starter_message_id(thread_id, message_id)

        try:
            summary = await sync_all_profile_stickies(
                guild,
                await context.profile_repo.list_all(),
                resolve_network_key=resolve_network_key,
                update_starter_message_id=update_starter_message_id,
                edit_view_factory=lambda thread_id: EditProfileView(self, thread_id),
            )
        except Exception:
            logger.exception("Profile sticky startup sync failed")
            return

        if summary.updated:
            await context.profile_cache.load_cache()

        logger.info(
            "Profile sticky startup sync complete",
            extra={
                "checked": summary.checked,
                "updated": summary.updated,
                "skipped": summary.skipped,
                "failed": summary.failed,
            },
        )

    async def _register_persistent_views(self) -> None:
        context = self.bot_context
        if context is None:
            return

        from bot.ui.join_views import JoinServerView, ModeratorReviewView
        from bot.ui.profile_views import EditProfileView

        for network in await context.network_repo.list_all():
            self.add_view(JoinServerView(self, network.key))

        for request in await context.server_request_repo.list_pending():
            self.add_view(ModeratorReviewView(self, request.id))

        for profile in await context.profile_repo.list_all():
            self.add_view(EditProfileView(self, profile.profile_thread_id))

    async def close(self) -> None:
        if self._topgg is not None:
            await self._topgg.close()
            self._topgg = None
        await self.db.close()
        await super().close()
