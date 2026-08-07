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
    ClientRepository,
    NetworkRepository,
    RelayRecordRepository,
    ServerRequestRepository,
    SettingsRepository,
)
from bot.services.bot_settings import BotSettingsService
from bot.services.client_cache import ClientCache
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
        self._slash_sync_started = False
        self._subscription_setup_synced = False

    async def setup_hook(self) -> None:
        await self.db.connect()
        self.schema_version = await migrations.run_migrations(self.db)

        network_repo = NetworkRepository(self.db)
        client_repo = ClientRepository(self.db)
        relay_record_repo = RelayRecordRepository(self.db)
        routing_service = RoutingService(network_repo, client_repo)
        client_cache = ClientCache(client_repo)
        await client_cache.load_cache()
        routing_service.attach_client_cache(client_cache)
        await routing_service.load_cache()

        settings_repo = SettingsRepository(self.db)
        server_request_repo = ServerRequestRepository(self.db)
        bot_settings = BotSettingsService(settings_repo, self.settings)
        await bot_settings.load()

        relay_service = RelayService(
            self.settings,
            routing_service,
            client_cache,
            client_repo,
            relay_record_repo,
        )

        self.bot_context = BotContext.create(
            self.settings,
            self.db,
            network_repo,
            client_repo,
            relay_record_repo,
            routing_service,
            client_cache,
            relay_service,
            bot_settings,
            settings_repo,
            server_request_repo,
        )
        self.bot_context.network_count = routing_service.network_count
        self.bot_context.client_count = client_cache.client_count
        self.bot_context.enabled_client_count = client_cache.enabled_client_count

        await self.load_extension("bot.cogs.servers")
        await self.load_extension("bot.cogs.relay")

        from bot.messages import validate_all_templates

        validate_all_templates()

        await self._register_persistent_views()

        guild = discord.Object(id=self.settings.guild_id)
        self.tree.copy_global_to(guild=guild)

    async def _sync_slash_commands(self) -> None:
        guild = discord.Object(id=self.settings.guild_id)
        try:
            synced = await asyncio.wait_for(
                self.tree.sync(guild=guild),
                timeout=30.0,
            )
            logger.info(
                "Slash commands synced to guild",
                extra={"guild_id": self.settings.guild_id, "command_count": len(synced)},
            )
        except TimeoutError:
            logger.error("Slash command sync timed out after 30s")
        except discord.Forbidden:
            logger.warning("Could not sync slash commands — re-invite the bot")
        except discord.HTTPException as exc:
            logger.warning("Slash command sync failed", extra={"error": str(exc)})

    async def on_ready(self) -> None:
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            logger.error(
                "Configured guild not visible to bot",
                extra={"guild_id": self.settings.guild_id},
            )
            return

        if not self._slash_sync_started:
            self._slash_sync_started = True
            asyncio.create_task(self._sync_slash_commands())

        context = self.bot_context
        logger.info(
            "Bot ready",
            extra={
                "guild_id": guild.id,
                "guild_name": guild.name,
                "user": str(self.user),
                "schema_version": self.schema_version,
                "network_count": context.network_count if context else 0,
                "client_count": context.client_count if context else 0,
                "latency_ms": round(self.latency * 1000),
            },
        )

        if self.settings.topgg_token and self._topgg is None:
            self._topgg = TopggService(self, self.settings.topgg_token)
            await self._topgg.start()

        if context is not None and not self._subscription_setup_synced:
            from bot.services.subscription_setup_sticky import sync_all_subscription_setups

            try:
                synced = await sync_all_subscription_setups(self, context, guild)
                self._subscription_setup_synced = True
                if synced:
                    logger.info(
                        "Synced subscription setup stickies",
                        extra={"subscription_count": synced},
                    )
            except Exception:
                logger.exception("Subscription setup sync on ready failed")

    async def _register_persistent_views(self) -> None:
        context = self.bot_context
        if context is None:
            return

        from bot.ui.join_views import JoinNetworkView, ModeratorReviewView
        from bot.ui.network_admin_views import NetworkAdminView
        from bot.ui.network_views import (
            NetworkProfileView,
            SubscribeSetupView,
            SubscriptionModerationView,
        )

        self.add_view(JoinNetworkView(self))
        self.add_view(NetworkAdminView(self))

        for request in await context.server_request_repo.list_pending():
            self.add_view(ModeratorReviewView(self, request.id))

        networks = await context.network_repo.list_all()
        network_keys = [n.key for n in networks]
        for client in await context.client_repo.list_all():
            self.add_view(
                NetworkProfileView(
                    self,
                    client.id,
                    network_keys,
                    timecode_enabled=client.timecode_enabled,
                ),
            )

        for sub in await context.client_repo.list_all_subscriptions():
            network_key = sub.network_key
            if not network_key and sub.network_id is not None:
                network = await context.network_repo.get_by_id(sub.network_id)
                if network is not None:
                    network_key = network.key
            if not network_key:
                network_key = "network"
            self.add_view(
                SubscriptionModerationView(
                    self,
                    sub.id,
                    network_key,
                    show_subscribe_connected=not sub.subscribe_confirmed,
                    show_blacklist=sub.subscribe_confirmed,
                )
            )
            if not sub.subscribe_confirmed:
                self.add_view(SubscribeSetupView(self, sub.id, network_key))

    async def close(self) -> None:
        if self._topgg is not None:
            await self._topgg.close()
            self._topgg = None
        await self.db.close()
        await super().close()
