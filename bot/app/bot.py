from __future__ import annotations

import asyncio
import importlib.metadata
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot.app.context import BotContext
from bot.app.discord import register_recipe_commands, register_recipe_events
from bot.app.features import build_recipe_registry
from bot.app.recipes import RecipeRegistry
from bot.core.clients.cache import ClientCache
from bot.core.database import migrations
from bot.core.database.connection import Database
from bot.core.database.store import Store
from bot.core.networks.routing import RoutingService
from bot.core.settings import BotSettingsService

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

        self.bot_context = BotContext.create(
            self.settings,
            self.db,
            store,
            routing_service,
            client_cache,
            None,
            bot_settings,
        )
        self.bot_context.network_count = routing_service.network_count
        self.bot_context.client_count = client_cache.client_count
        self.bot_context.enabled_client_count = client_cache.enabled_client_count

        await self.recipe_registry.dispatch("app.services")
        register_recipe_commands(self)
        register_recipe_events(self)

        await self.recipe_registry.dispatch("app.setup")

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
                "bot_version": importlib.metadata.version("the-network"),
                "schema_version": self.schema_version,
                "network_count": context.network_count if context else 0,
                "client_count": context.client_count if context else 0,
                "latency_ms": round(self.latency * 1000),
            },
        )

        if context is not None:
            try:
                await self.recipe_registry.dispatch("app.ready", guild=guild)
            except Exception:
                logger.exception("Ready recipe dispatch failed")

    async def close(self) -> None:
        await self.db.close()
        await super().close()
