from __future__ import annotations

import asyncio
import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from bot.app.context import BotContext
from bot.app.discord import register_recipe_commands, register_recipe_events
from bot.app.features import build_recipe_registry
from bot.app.recipes import RecipeRegistry
from bot.app.triggers import TriggerCatalog, build_trigger_catalog, dispatch, dispatch_event
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
        self.trigger_catalog: TriggerCatalog = build_trigger_catalog()
        self.schema_version: int = 0
        self._slash_sync_started = False
        self._subscription_setup_synced = False
        self._changelog_synced = False

    async def dispatch_trigger(self, trigger_id: str, **payload: Any) -> Any:
        return await dispatch(
            self.trigger_catalog,
            self.recipe_registry.run,
            trigger_id,
            **payload,
        )

    async def dispatch_event(self, event: str, **payload: Any) -> list[Any]:
        return await dispatch_event(
            self.trigger_catalog,
            self.recipe_registry.run,
            event,
            **payload,
        )

    def make_view_registry(self) -> Any:
        from bot.app.widgets import PersistentViewRegistry

        return PersistentViewRegistry(self)

    def templates_view(self, template_id: str, **values: Any) -> Any:
        from bot.app.widgets.drafts import view

        return view(template_id, **values)

    def templates_modal(self, template_id: str, **values: Any) -> Any:
        from bot.app.widgets.drafts import modal

        return modal(template_id, **values)

    def render_named_view(self, name: str, **params: Any) -> Any:
        from bot.features.widgets.builders import build_named_view

        return build_named_view(self, name, **params)

    def render_named_modal(
        self,
        name: str,
        *,
        params: dict[str, Any] | None = None,
        field_defaults: dict[str, str] | None = None,
    ) -> Any:
        from bot.features.widgets.builders import build_named_modal

        return build_named_modal(self, name, params=params, field_defaults=field_defaults)

    def render_view(self, name: str, **params: Any) -> Any:
        return self.render_named_view(name, **params)

    async def present_migration_review(self, interaction: Any, plan: Any) -> Any:
        from bot.app.widgets.migration import present_migration_review

        return await present_migration_review(interaction, plan)

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

        await self.dispatch_event("app.services")
        register_recipe_commands(self)
        register_recipe_events(self)

        from bot.app.triggers.validate import validate_template_triggers
        from bot.app.widgets import validate_widget_templates

        validate_template_triggers()
        validate_widget_templates()

        await self.dispatch_event("app.setup")

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
                await self.dispatch_event("app.ready", guild=guild)
            except Exception:
                logger.exception("Ready recipe dispatch failed")

    async def close(self) -> None:
        await self.db.close()
        await super().close()
