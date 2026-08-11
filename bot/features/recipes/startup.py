from __future__ import annotations

import logging

import discord

from bot.app.layout import validate_all_layouts
from bot.app.recipes import RecipeContext, recipe
from bot.app.templates import validate_all_templates
from bot.features.channels.stickies import validate_sticky_catalog
from bot.features.channels.stickies.subscription import sync_all_subscription_setups
from bot.features.hub.changelog import sync_changelog_on_ready
from bot.features.relay.service import RelayService
from bot.features.widgets.views.join_views import JoinNetworkView, ModeratorReviewView
from bot.features.widgets.views.network_admin_views import NetworkAdminView
from bot.features.widgets.views.network_views import (
    NetworkProfileView,
    SubscribeSetupView,
    SubscriptionModerationView,
)
from bot.features.widgets.views.persistent_views import PersistentViewRegistry

logger = logging.getLogger(__name__)


@recipe("app.initialize_relay", events=("app.services",))
async def initialize_relay(recipe_context: RecipeContext) -> None:
    context = recipe_context.core
    context.relay_service = RelayService(
        context.settings,
        context.routing_service,
        context.client_cache,
        context.store.clients,
        context.store.relay,
    )


@recipe("app.validate_features", events=("app.setup",))
async def validate_features(recipe_context: RecipeContext) -> None:
    del recipe_context
    validate_all_templates()
    validate_all_layouts()
    validate_sticky_catalog()


@recipe("app.register_persistent_views", events=("app.setup",))
async def register_persistent_views(recipe_context: RecipeContext) -> None:
    bot = recipe_context.bot
    context = recipe_context.core
    bot.add_view(JoinNetworkView(bot))
    bot.add_view(NetworkAdminView(bot))

    for request in await context.store.requests.list_pending():
        bot.add_view(ModeratorReviewView(bot, request.id))

    networks = await context.store.networks.list_all()
    network_keys = [network.key for network in networks]
    for client in await context.store.clients.list_all():
        bot.add_view(
            NetworkProfileView(
                bot,
                client.id,
                network_keys,
                timecode_enabled=client.timecode_enabled,
            )
        )

    for subscription in await context.store.clients.list_all_subscriptions():
        network_key = subscription.network_key
        if not network_key and subscription.network_id is not None:
            network = await context.store.networks.get_by_id(subscription.network_id)
            if network is not None:
                network_key = network.key
        network_key = network_key or "network"
        bot.add_view(
            SubscriptionModerationView(
                bot,
                subscription.id,
                network_key,
                show_subscribe_connected=not subscription.subscribe_confirmed,
                show_blacklist=subscription.subscribe_confirmed,
            )
        )
        if not subscription.subscribe_confirmed:
            bot.add_view(SubscribeSetupView(bot, subscription.id, network_key))


@recipe("app.sync_subscription_stickies", events=("app.ready",))
async def sync_subscription_stickies(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
) -> None:
    bot = recipe_context.bot
    if getattr(bot, "_subscription_setup_synced", False):
        return
    synced = await sync_all_subscription_setups(
        bot,
        recipe_context.core,
        guild,
        view_registry=PersistentViewRegistry(bot),
    )
    bot._subscription_setup_synced = True
    if synced:
        logger.info("Synced subscription setup stickies", extra={"subscription_count": synced})


@recipe("app.sync_changelog", events=("app.ready",))
async def sync_changelog(recipe_context: RecipeContext, *, guild: discord.Guild) -> None:
    bot = recipe_context.bot
    if getattr(bot, "_changelog_synced", False):
        return
    await sync_changelog_on_ready(bot, recipe_context.core, guild)
    bot._changelog_synced = True
