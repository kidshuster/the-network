"""Startup / ready-time feature recipes."""

from __future__ import annotations

import logging

import discord

from bot.contracts.recipes import RecipeContext, recipe

logger = logging.getLogger(__name__)


@recipe("app.initialize_relay")
async def initialize_relay(recipe_context: RecipeContext) -> None:
    from bot.features.recipes.hub.relay.service import RelayService

    context = recipe_context.core
    context.relay_service = RelayService(
        context.settings,
        context.routing_service,
        context.client_cache,
        context.store.clients,
        context.store.relay,
    )


@recipe("app.validate_features")
async def validate_features(recipe_context: RecipeContext) -> None:
    from bot.core.templates import validate_all_templates
    from bot.features.channels.layout import validate_all_layouts
    from bot.features.channels.stickies import validate_sticky_catalog

    del recipe_context
    validate_all_templates()
    validate_all_layouts()
    validate_sticky_catalog()


@recipe("app.register_persistent_views")
async def register_persistent_views(recipe_context: RecipeContext) -> None:
    bot = recipe_context.bot
    context = recipe_context.core
    bot.add_view(bot.render_view("join_network"))
    bot.add_view(bot.render_view("network_admin"))

    for request in await context.store.requests.list_pending():
        bot.add_view(bot.render_view("moderator_review", request_id=request.id))

    networks = await context.store.networks.list_all()
    network_keys = [network.key for network in networks]
    for client in await context.store.clients.list_all():
        bot.add_view(
            bot.render_view(
                "network_profile",
                client_id=client.id,
                network_keys=network_keys,
                timecode_enabled=client.timecode_enabled,
                read_only=client.read_only,
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
            bot.render_view(
                "subscription_moderation",
                subscription_id=subscription.id,
                network_key=network_key,
                show_subscribe_connected=not subscription.subscribe_confirmed,
                show_blacklist=subscription.subscribe_confirmed,
            )
        )
        if not subscription.subscribe_confirmed:
            bot.add_view(
                bot.render_view(
                    "subscribe_setup",
                    subscription_id=subscription.id,
                    network_key=network_key,
                )
            )


@recipe("startup.ready")
async def startup_ready(recipe_context: RecipeContext, *, guild: discord.Guild) -> None:
    """Idempotent ready-time feature synchronization."""
    from bot.features.channels.stickies.subscription import sync_all_subscription_setups
    from bot.features.recipes.hub.changelog import sync_changelog_on_ready

    bot = recipe_context.bot
    context = recipe_context.core

    if not getattr(bot, "_subscription_setup_synced", False):
        synced = await sync_all_subscription_setups(
            bot,
            context,
            guild,
            view_registry=bot.make_view_registry(),
        )
        bot._subscription_setup_synced = True
        if synced:
            logger.info(
                "Synced subscription setup stickies",
                extra={"subscription_count": synced},
            )

    if not getattr(bot, "_changelog_synced", False):
        await sync_changelog_on_ready(bot, context, guild)
        bot._changelog_synced = True
