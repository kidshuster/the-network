from __future__ import annotations

import logging
from typing import Any

import discord

from bot.core.models.errors import NetworkValidationError
from bot.errors import UserFacingError
from bot.widgets.recipes.metadata import CommandSpec
from bot.widgets.recipes.registry import RecipeRegistry, collect_recipes, recipe
from bot.widgets.recipes.runtime import RecipeContext

logger = logging.getLogger(__name__)


@recipe(
    "server.init",
    command=CommandSpec(
        group="server",
        name="init",
        description="Set up hub categories/channels and run permission smoke checks",
        default_permissions=("manage_guild",),
        background=True,
        presenter="server.init",
        group_description="Initialize and maintain the Discord hub server",
    ),
)
async def initialize_server(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> Any:
    from bot.widgets.recipes.hub.initialize import initialize_guild
    from bot.widgets.views.persistent_views import PersistentViewRegistry

    guild = interaction.guild
    if guild is None or guild.id != recipe_context.bot.settings.guild_id:
        raise UserFacingError("This command can only be used in the configured hub guild.")
    bot_member = guild.me
    if bot_member is None:
        raise UserFacingError("Bot member is unavailable.")
    core = recipe_context.core
    return await initialize_guild(
        guild,
        bot_member,
        access_role_name=recipe_context.bot.settings.network_access_role_name,
        operator_role_name=recipe_context.bot.settings.network_operator_role_name,
        clients=await core.store.clients.list_all(),
        bot=recipe_context.bot,
        context=core,
        view_registry=PersistentViewRegistry(recipe_context.bot),
    )


@recipe(
    "server.probe",
    command=CommandSpec(
        group="server",
        name="probe",
        description="Run read-only checks for hub permissions, layout, and community slots",
        default_permissions=("manage_guild",),
        background=True,
        presenter="server.probe",
        group_description="Initialize and maintain the Discord hub server",
    ),
)
async def probe_server(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> Any:
    from bot.core.hub.probe import run_server_probe

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


@recipe(
    "server.uninit",
    command=CommandSpec(
        group="server",
        name="uninit",
        description="Remove managed hub resources while preserving community channels",
        default_permissions=("manage_guild",),
        background=True,
        presenter="server.uninit",
        group_description="Initialize and maintain the Discord hub server",
    ),
)
async def uninitialize_server(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> Any:
    from bot.core.hub.data_reset import reset_hub_layout_data
    from bot.widgets.recipes.hub.uninitialize import uninitialize_guild

    guild = interaction.guild
    if guild is None or guild.id != recipe_context.bot.settings.guild_id:
        raise UserFacingError("This command can only be used in the configured hub guild.")
    bot_member = guild.me
    if bot_member is None:
        raise UserFacingError("Bot member is unavailable.")
    result = await uninitialize_guild(
        guild,
        bot_member,
        access_role_name=recipe_context.bot.settings.network_access_role_name,
        operator_role_name=recipe_context.bot.settings.network_operator_role_name,
    )
    data_result = await reset_hub_layout_data(recipe_context.core, guild.id)
    if (note := data_result.summary_note()) is not None:
        result.notes.append(note)
    return result


@recipe(
    "server.sync_join_guide",
    command=CommandSpec(
        group="server",
        name="sync-join-guide",
        description="Refresh the join guide in the join-the-network channel",
        default_permissions=("manage_guild",),
        presenter="server.sync_join_guide",
        group_description="Initialize and maintain the Discord hub server",
    ),
)
async def sync_join_guide(
    recipe_context: RecipeContext, *, interaction: discord.Interaction
) -> tuple[Any, discord.TextChannel]:
    from bot.channels.resolve import (
        HUB_CATEGORY_NETWORK,
        HUB_CHANNEL_JOIN_THE_NETWORK,
        resolve_hub_category,
        resolve_hub_channel,
    )
    from bot.channels.stickies.join import sync_hub_join_sticky
    from bot.widgets.views.persistent_views import PersistentViewRegistry

    guild = interaction.guild
    if guild is None or guild.me is None:
        raise UserFacingError("Guild or bot member is unavailable.")
    network_hub = resolve_hub_category(guild, HUB_CATEGORY_NETWORK)
    channel = resolve_hub_channel(
        guild,
        HUB_CHANNEL_JOIN_THE_NETWORK,
        category_id=None if network_hub is None else network_hub.id,
    )
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


@recipe("hub.handle_announcement")
async def handle_announcement(recipe_context: RecipeContext, *, message: discord.Message) -> None:
    from bot.core.hub.announcements import handle_network_announcements_message

    await handle_network_announcements_message(recipe_context.bot, message)


@recipe("relay.deliver")
async def relay_message(recipe_context: RecipeContext, *, message: discord.Message) -> Any:
    service = recipe_context.core.relay_service
    if not service.is_potential_feed_message(message):
        return None
    result = await service.relay_message(message)
    if result is None and (reason := service.feed_reject_reason(message)) is not None:
        logger.info(
            "Publish message not relayed",
            extra={
                "source_message_id": message.id,
                "channel_id": message.channel.id,
                "reason": reason,
            },
        )
    return result


@recipe("relay.on_message", events=("discord.message",))
async def on_message(recipe_context: RecipeContext, *, message: discord.Message) -> Any:
    await recipe_context.run("hub.handle_announcement", message=message)
    return await recipe_context.run("relay.deliver", message=message)


@recipe("subscription.webhook_updated", events=("discord.webhooks_update",))
async def webhook_updated(
    recipe_context: RecipeContext, *, channel: discord.abc.GuildChannel
) -> Any:
    from bot.channels.stickies.subscription import (
        sync_subscription_setup_by_publish_channel,
    )
    from bot.widgets.views.persistent_views import PersistentViewRegistry

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


@recipe("network.create")
async def create_network(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    key: str,
    display_name: str,
    view_registry: Any,
) -> tuple[Any, int, int]:
    from bot.core.clients.profile_sync import refresh_all_client_profiles
    from bot.core.clients.subscription import resync_subscriptions_for_network

    core = recipe_context.core
    existing = await core.store.networks.get_by_key(key)
    if existing is not None:
        raise NetworkValidationError(f"Network `{existing.key}` already exists.")
    network = await core.store.networks.create(
        guild_id=guild.id, key=key, display_name=display_name
    )
    await core.refresh_network_counts()
    relinked = await resync_subscriptions_for_network(
        guild,
        recipe_context.bot,
        core,
        network,
        access_role_name=recipe_context.bot.settings.network_access_role_name,
        view_registry=view_registry,
    )
    updated = await refresh_all_client_profiles(
        recipe_context.bot, core, guild, view_registry=view_registry
    )
    return network, updated, relinked


@recipe("network.delete")
async def delete_network(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    key: str,
    view_registry: Any,
) -> Any:
    from bot.core.clients.profile_sync import refresh_all_client_profiles

    core = recipe_context.core
    network = await core.store.networks.get_by_key(key)
    if network is None:
        raise NetworkValidationError(f"Network `{key.strip().lower()}` was not found.")
    await core.store.networks.delete_with_relations(key)
    await core.refresh_projections()
    await refresh_all_client_profiles(recipe_context.bot, core, guild, view_registry=view_registry)
    return network


def build_recipe_registry(bot: Any) -> RecipeRegistry:
    registry = RecipeRegistry(bot)
    registry.register_many(collect_recipes(__import__(__name__, fromlist=["*"])))
    return registry


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
    from bot.core.clients.profile_post import build_client_profile_embed
    from bot.core.clients.profile_sync import refresh_client_profile_message
    from bot.core.clients.provision import ClientProvisionService
    from bot.core.media.emoji import EmojiService, emoji_sync_target_from_client
    from bot.widgets.recipes.onboarding.service import _ProvisionOutcome

    bot = recipe_context.bot
    core = recipe_context.core
    provision = await ClientProvisionService().provision_client(
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
