from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot.adapters.discord import register_recipe_commands, register_recipe_events
from bot.core.clients.cache import ClientCache
from bot.core.database import migrations
from bot.core.database.connection import Database
from bot.core.database.store import Store
from bot.core.networks.routing import RoutingService
from bot.core.relay.service import RelayService
from bot.core.runtime import BotContext
from bot.core.settings import BotSettingsService
from bot.widgets.recipes import RecipeRegistry, build_recipe_registry

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
        self.recipe_registry: RecipeRegistry = build_recipe_registry(self)
        self.schema_version: int = 0
        self._slash_sync_started = False
        self._subscription_setup_synced = False
        self._changelog_synced = False

    async def setup_hook(self) -> None:
        await self.db.connect()
        self.schema_version = await migrations.run_migrations(self.db)

        store = Store.create(self.db)
        routing_service = RoutingService(store.networks, store.clients)
        client_cache = ClientCache(store.clients)
        await client_cache.load_cache()
        routing_service.attach_client_cache(client_cache)
        await routing_service.load_cache()

        bot_settings = BotSettingsService(store.settings, self.settings)
        await bot_settings.load()

        relay_service = RelayService(
            self.settings,
            routing_service,
            client_cache,
            store.clients,
            store.relay,
        )

        self.bot_context = BotContext.create(
            self.settings,
            self.db,
            store,
            routing_service,
            client_cache,
            relay_service,
            bot_settings,
        )
        self.bot_context.network_count = routing_service.network_count
        self.bot_context.client_count = client_cache.client_count
        self.bot_context.enabled_client_count = client_cache.enabled_client_count

        register_recipe_commands(self)
        register_recipe_events(self)

        from bot.channels.layout import validate_all_layouts
        from bot.channels.stickies import validate_sticky_catalog
        from bot.widgets import validate_all_templates

        validate_all_templates()
        validate_all_layouts()
        validate_sticky_catalog()

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
        from bot.core.hub.changelog import installed_version

        logger.info(
            "Bot ready",
            extra={
                "guild_id": guild.id,
                "guild_name": guild.name,
                "user": str(self.user),
                "bot_version": installed_version(),
                "schema_version": self.schema_version,
                "network_count": context.network_count if context else 0,
                "client_count": context.client_count if context else 0,
                "latency_ms": round(self.latency * 1000),
            },
        )

        if context is not None and not self._subscription_setup_synced:
            from bot.channels.stickies.subscription import sync_all_subscription_setups
            from bot.widgets.views.persistent_views import PersistentViewRegistry

            try:
                synced = await sync_all_subscription_setups(
                    self,
                    context,
                    guild,
                    view_registry=PersistentViewRegistry(self),
                )
                self._subscription_setup_synced = True
                if synced:
                    logger.info(
                        "Synced subscription setup stickies",
                        extra={"subscription_count": synced},
                    )
            except Exception:
                logger.exception("Subscription setup sync on ready failed")

        if context is not None and not self._changelog_synced:
            from bot.core.hub.changelog import sync_changelog_on_ready

            try:
                await sync_changelog_on_ready(self, context, guild)
                self._changelog_synced = True
            except Exception:
                logger.exception("Changelog sync on ready failed")

    async def _register_persistent_views(self) -> None:
        context = self.bot_context
        if context is None:
            return

        from bot.widgets.views.join_views import JoinNetworkView, ModeratorReviewView
        from bot.widgets.views.network_admin_views import NetworkAdminView
        from bot.widgets.views.network_views import (
            NetworkProfileView,
            SubscribeSetupView,
            SubscriptionModerationView,
        )

        self.add_view(JoinNetworkView(self))
        self.add_view(NetworkAdminView(self))

        for request in await context.store.requests.list_pending():
            self.add_view(ModeratorReviewView(self, request.id))

        networks = await context.store.networks.list_all()
        network_keys = [n.key for n in networks]
        for client in await context.store.clients.list_all():
            self.add_view(
                NetworkProfileView(
                    self,
                    client.id,
                    network_keys,
                    timecode_enabled=client.timecode_enabled,
                ),
            )

        for sub in await context.store.clients.list_all_subscriptions():
            network_key = sub.network_key
            if not network_key and sub.network_id is not None:
                network = await context.store.networks.get_by_id(sub.network_id)
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
        await self.db.close()
        await super().close()
