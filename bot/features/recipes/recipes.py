"""Index of server-process recipes.

Entry surfaces (slash, Discord/app events, UI) are registered under
``bot/app/triggers/``. This module only defines ``@recipe`` callables.
"""

from __future__ import annotations

import logging
from typing import Any

import discord

from bot.app.recipes import RecipeContext, recipe
from bot.errors import UserFacingError

logger = logging.getLogger(__name__)


@recipe("server.init")
async def initialize_server(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> Any:
    guild = interaction.guild
    if guild is None or guild.id != recipe_context.bot.settings.guild_id:
        raise UserFacingError("This command can only be used in the configured hub guild.")
    bot_member = guild.me
    if bot_member is None:
        raise UserFacingError("Bot member is unavailable.")
    return await recipe_context.run(
        "hub.initialize",
        guild=guild,
        bot_member=bot_member,
        interaction=interaction,
    )


@recipe("server.probe")
async def probe_server(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> Any:
    from bot.features.recipes.hub.probe import run_server_probe

    guild = interaction.guild
    if guild is None or guild.id != recipe_context.bot.settings.guild_id:
        raise UserFacingError("This command can only be used in the configured hub guild.")
    bot_member = guild.me
    if bot_member is None:
        raise UserFacingError("Bot member is unavailable.")
    return await run_server_probe(
        guild,
        bot_member,
        settings=recipe_context.bot.settings,
        context=recipe_context.core,
    )


@recipe("server.uninit")
async def uninitialize_server(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> Any:
    guild = interaction.guild
    if guild is None or guild.id != recipe_context.bot.settings.guild_id:
        raise UserFacingError("This command can only be used in the configured hub guild.")
    bot_member = guild.me
    if bot_member is None:
        raise UserFacingError("Bot member is unavailable.")
    await recipe_context.run("hub.teardown_installs", guild_id=guild.id)
    result = await recipe_context.run(
        "hub.uninitialize",
        guild=guild,
        bot_member=bot_member,
    )
    data_result = await recipe_context.run("hub.reset_data", guild_id=guild.id)
    if (note := data_result.summary_note()) is not None:
        result.notes.append(note)
    return result


@recipe("server.sync_join_guide")
async def sync_join_guide(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> tuple[Any, discord.TextChannel]:
    from bot.app.widgets import PersistentViewRegistry
    from bot.features.channels.resolve import resolve_join_the_network_channel
    from bot.features.channels.stickies.join import sync_hub_join_sticky

    guild = interaction.guild
    if guild is None or guild.me is None:
        raise UserFacingError("Guild or bot member is unavailable.")
    channel = resolve_join_the_network_channel(guild)
    if channel is None:
        raise UserFacingError("The join-the-network channel was not found.")
    view = PersistentViewRegistry(recipe_context.bot).register_join_network_view()
    result = await sync_hub_join_sticky(
        guild,
        guild.me,
        channel,
        view,
        get_setting=recipe_context.core.store.settings.get,
        set_setting=recipe_context.core.store.settings.set,
        wipe_channel=True,
    )
    return result, channel


@recipe("relay.on_message")
async def on_message(recipe_context: RecipeContext, *, message: discord.Message) -> Any:
    await recipe_context.run("hub.handle_announcement", message=message)
    return await recipe_context.run("relay.deliver", message=message)


@recipe("subscription.webhook_updated")
async def webhook_updated(
    recipe_context: RecipeContext, *, channel: discord.abc.GuildChannel
) -> Any:
    from bot.app.widgets import PersistentViewRegistry
    from bot.features.channels.stickies.subscription import (
        sync_subscription_setup_by_publish_channel,
    )

    if not isinstance(channel, discord.TextChannel):
        return None
    return await sync_subscription_setup_by_publish_channel(
        recipe_context.bot,
        recipe_context.core,
        channel.guild,
        channel.id,
        view_registry=PersistentViewRegistry(recipe_context.bot),
    )


@recipe("text.parse_dates")
async def parse_dates(recipe_context: RecipeContext, *, text: str) -> str:
    del recipe_context
    from bot.core.parsers.date_parser import replace_dates

    return replace_dates(text)


@recipe("blacklist.replace")
async def replace_blacklist(
    recipe_context: RecipeContext,
    *,
    subscription_id: int,
    selected_client_ids: list[str] | tuple[str, ...] | set[str],
) -> int:
    repo = recipe_context.core.store.clients
    subscription = await repo.get_subscription_by_id(subscription_id)
    if subscription is None or subscription.network_id is None:
        raise ValueError("Subscription was not found.")
    allowed = {
        item.client_id
        for item in await repo.list_subscriptions_by_network(subscription.network_id)
        if item.client_id != subscription.client_id
    }
    selected = {int(value) for value in selected_client_ids} & allowed
    current = set(await repo.list_blacklisted_client_ids(subscription_id)) & allowed
    for client_id in selected - current:
        await repo.add_blacklist(subscription_id, client_id)
    for client_id in current - selected:
        await repo.remove_blacklist(subscription_id, client_id)
    return len(selected)


@recipe("client.provision_from_request")
async def provision_client_from_request(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    request: Any,
    image: Any,
    view_registry: Any,
) -> Any:
    from bot.core.media.emoji import EmojiService, emoji_sync_target_from_client
    from bot.features.recipes.hub.clients.profile_post import build_client_profile_embed
    from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message
    from bot.features.recipes.hub.clients.provision import provision_client
    from bot.features.recipes.hub.onboarding.service import _ProvisionOutcome

    bot = recipe_context.bot
    core = recipe_context.core
    provision = await provision_client(
        guild,
        bot_member,
        server_name=request.server_name,
        access_role_name=bot.settings.network_access_role_name,
        operator_role_name=bot.settings.network_operator_role_name,
    )
    network_keys = [network.key for network in await core.store.networks.list_all()]
    starter = await provision.profile_channel.send(
        embed=build_client_profile_embed(
            server_name=request.server_name,
            display_name=request.display_name,
            enabled=True,
        ),
        view=view_registry.register_client_profile_view(0, network_keys),
        silent=True,
    )
    client = await core.store.clients.create(
        guild_id=guild.id,
        server_name=request.server_name,
        display_name=request.display_name,
        category_id=provision.category.id,
        client_role_id=provision.client_role.id,
        profile_channel_id=provision.profile_channel.id,
        profile_message_id=starter.id,
    )
    await starter.edit(view=view_registry.register_client_profile_for_client(client, network_keys))
    emoji = await EmojiService().sync_for_profile(
        guild,
        emoji_sync_target_from_client(client, source_channel_id=provision.profile_channel.id),
        image,
        previous_hash=None,
        previous_emoji_id=None,
        force=True,
    )
    if emoji.emoji_id is not None:
        await core.store.clients.update_emoji_fields(
            client.id,
            emoji_id=emoji.emoji_id,
            emoji_name=emoji.emoji_name,
            image_hash=emoji.image_hash,
            degraded_reason=emoji.degraded_reason,
        )
        client = await core.store.clients.get_by_id(client.id) or client
    await refresh_client_profile_message(bot, core, guild, client, view_registry=view_registry)
    return _ProvisionOutcome(
        success=True,
        client_role=provision.client_role,
        profile_channel=provision.profile_channel,
    )


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
    from bot.app.layout import validate_all_layouts
    from bot.app.templates import validate_all_templates
    from bot.app.triggers.validate import validate_template_triggers
    from bot.app.widgets import validate_widget_templates
    from bot.features.channels.stickies import validate_sticky_catalog

    del recipe_context
    validate_all_templates()
    validate_all_layouts()
    validate_sticky_catalog()
    validate_template_triggers()
    validate_widget_templates()


@recipe("app.register_persistent_views")
async def register_persistent_views(recipe_context: RecipeContext) -> None:
    from bot.app.widgets import PersistentViewRegistry, render_view

    bot = recipe_context.bot
    context = recipe_context.core
    bot.add_view(render_view("join_network", bot))
    bot.add_view(render_view("network_admin", bot))

    for request in await context.store.requests.list_pending():
        bot.add_view(render_view("moderator_review", bot, request_id=request.id))

    networks = await context.store.networks.list_all()
    network_keys = [network.key for network in networks]
    for client in await context.store.clients.list_all():
        bot.add_view(
            render_view(
                "network_profile",
                bot,
                client_id=client.id,
                network_keys=network_keys,
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
            render_view(
                "subscription_moderation",
                bot,
                subscription_id=subscription.id,
                network_key=network_key,
                show_subscribe_connected=not subscription.subscribe_confirmed,
                show_blacklist=subscription.subscribe_confirmed,
            )
        )
        if not subscription.subscribe_confirmed:
            bot.add_view(
                render_view(
                    "subscribe_setup",
                    bot,
                    subscription_id=subscription.id,
                    network_key=network_key,
                )
            )
    del PersistentViewRegistry


@recipe("app.sync_subscription_stickies")
async def sync_subscription_stickies(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
) -> None:
    from bot.app.widgets import PersistentViewRegistry
    from bot.features.channels.stickies.subscription import sync_all_subscription_setups

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


@recipe("app.sync_changelog")
async def sync_changelog(recipe_context: RecipeContext, *, guild: discord.Guild) -> None:
    from bot.features.recipes.hub.changelog import sync_changelog_on_ready

    bot = recipe_context.bot
    if getattr(bot, "_changelog_synced", False):
        return
    await sync_changelog_on_ready(bot, recipe_context.core, guild)
    bot._changelog_synced = True
