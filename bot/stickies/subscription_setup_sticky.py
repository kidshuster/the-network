from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import discord

from bot.clients.resources import fetch_publish_channel, fetch_subscribe_channel
from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.domain.network import Network
from bot.messages import render_embed
from bot.stickies.subscription_setup import SubscriptionSetupState, resolve_setup_state
from bot.stickies.sync import (
    SETUP_STICKY_HISTORY_LIMIT,
    find_embed_sticky_by_footer_scan,
    resolve_embed_sticky_message,
    sync_footer_marker_embed_sticky,
)
from bot.ui.view_registry import ViewRegistry

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

SetupMode = Literal["create", "reconcile"]

_PUBLISH_SETUP_FOOTER = "publish setup"
_SUBSCRIBE_SETUP_FOOTER = "subscribe setup"
_SETUP_HISTORY_LIMIT = SETUP_STICKY_HISTORY_LIMIT


def _bot_author_icon_url(bot: NetworkRelayBot) -> str:
    user = bot.user
    if user is None:
        return ""
    return str(user.display_avatar.url)


async def _publish_announcement(message: discord.Message) -> None:
    publish = getattr(message, "publish", None)
    if publish is None:
        return
    try:
        await message.publish()
    except discord.HTTPException as exc:
        logger.warning(
            "Could not publish announcement message",
            extra={"message_id": message.id, "error": str(exc)},
        )


async def _broadcast_network_member_welcome(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    *,
    client: Client,
    subscription: ClientSubscription,
    network: Network,
) -> None:
    """Notify other network members that a client finished connecting."""
    from bot.hub.announcements import is_hub_announcements_client

    if is_hub_announcements_client(client, context.settings):
        return
    embed = render_embed(
        "network_member_connected",
        author_icon_url=_bot_author_icon_url(bot),
        network_display_name=network.display_name,
        network_key=network.key,
        client_server_name=client.server_name,
    )
    for dest_sub in context.routing_service.list_network_subscriptions(network.id):
        if (
            dest_sub.id == subscription.id
            or dest_sub.client_id == client.id
            or dest_sub.subscribe_channel_id == subscription.subscribe_channel_id
            or not dest_sub.enabled
        ):
            continue
        if await context.store.clients.is_blacklisted(dest_sub.id, client.id):
            continue
        dest_client = context.client_cache.get_client(dest_sub.client_id)
        if dest_client is None or not dest_client.enabled:
            continue
        from bot.hub.announcements import is_hub_announcements_client

        if is_hub_announcements_client(dest_client, context.settings):
            continue
        channel = guild.get_channel(dest_sub.subscribe_channel_id)
        if channel is None or not hasattr(channel, "send"):
            continue
        try:
            sent = await channel.send(embed=embed, silent=True)
        except discord.HTTPException:
            logger.warning(
                "Could not post network member welcome",
                extra={
                    "subscription_id": dest_sub.id,
                    "subscribe_channel_id": dest_sub.subscribe_channel_id,
                },
            )
            continue
        await _publish_announcement(sent)


async def _delete_setup_message(
    guild: discord.Guild,
    channel_id: int,
    message_id: int | None,
) -> None:
    if message_id is None:
        return
    channel = guild.get_channel(channel_id)
    if channel is None or not hasattr(channel, "fetch_message"):
        return
    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
    except discord.HTTPException:
        pass


def _supports_setup_sticky(channel: discord.abc.GuildChannel) -> bool:
    return hasattr(channel, "history") and hasattr(channel, "send")


_find_setup_sticky_by_scan = find_embed_sticky_by_footer_scan
_resolve_setup_sticky_message = resolve_embed_sticky_message


async def _sync_publish_setup_sticky(
    guild: discord.Guild,
    subscription: ClientSubscription,
    *,
    publish_channel: discord.TextChannel,
    context: BotContext,
    bot_user_id: int,
    configured: bool,
    allow_create: bool,
) -> ClientSubscription:
    result = await sync_footer_marker_embed_sticky(
        publish_channel,
        bot_user_id=bot_user_id,
        stored_message_id=subscription.publish_setup_message_id,
        footer_marker=_PUBLISH_SETUP_FOOTER,
        embed=render_embed(
            "publish_setup_instructions",
            publish_mention=publish_channel.mention,
        ),
        allow_create=allow_create,
        remove=configured,
    )
    if result.removed:
        if subscription.publish_setup_message_id is not None:
            return await context.store.clients.update_publish_setup_message_id(
                subscription.id,
                None,
            )
        return subscription
    if result.message is None:
        return subscription
    if subscription.publish_setup_message_id != result.message.id:
        return await context.store.clients.update_publish_setup_message_id(
            subscription.id,
            result.message.id,
        )
    return subscription


async def _sync_subscribe_setup_sticky(
    guild: discord.Guild,
    subscription: ClientSubscription,
    *,
    subscribe_channel: discord.abc.GuildChannel,
    context: BotContext,
    network: Network,
    bot_user_id: int,
    confirmed: bool,
    allow_create: bool,
    view_registry: ViewRegistry,
) -> ClientSubscription:
    if confirmed:
        result = await sync_footer_marker_embed_sticky(
            subscribe_channel,
            bot_user_id=bot_user_id,
            stored_message_id=subscription.subscribe_setup_message_id,
            footer_marker=_SUBSCRIBE_SETUP_FOOTER,
            embed=discord.Embed(),
            allow_create=False,
            remove=True,
        )
        if result.removed and subscription.subscribe_setup_message_id is not None:
            return await context.store.clients.update_subscribe_setup_message_id(
                subscription.id,
                None,
            )
        return subscription

    if not _supports_setup_sticky(subscribe_channel):
        return subscription

    embed = render_embed(
        "subscribe_setup_instructions",
        subscribe_mention=subscribe_channel.mention,
        network_channel_name=f"🌐-{network.display_name}",
    )
    view = view_registry.register_subscribe_setup_view(subscription.id, network.key)
    result = await sync_footer_marker_embed_sticky(
        subscribe_channel,
        bot_user_id=bot_user_id,
        stored_message_id=subscription.subscribe_setup_message_id,
        footer_marker=_SUBSCRIBE_SETUP_FOOTER,
        embed=embed,
        view=view,
        allow_create=allow_create,
        remove=False,
    )
    if result.message is None:
        return subscription
    if subscription.subscribe_setup_message_id != result.message.id:
        return await context.store.clients.update_subscribe_setup_message_id(
            subscription.id,
            result.message.id,
        )
    return subscription


async def _maybe_post_activation_welcome(
    bot: NetworkRelayBot,
    subscription: ClientSubscription,
    *,
    subscribe_channel: discord.abc.GuildChannel,
    context: BotContext,
    guild: discord.Guild,
    network: Network,
    client: Client,
    setup_state: SubscriptionSetupState,
) -> ClientSubscription:
    """Post a one-time server-connected embed when a network subscription first activates."""
    from bot.hub.announcements import is_hub_announcements_client

    if is_hub_announcements_client(client, context.settings):
        return subscription
    if not setup_state.fully_configured:
        return subscription
    if not hasattr(subscribe_channel, "send"):
        return subscription

    fresh = await context.store.clients.get_subscription_by_id(subscription.id)
    if fresh is None:
        return subscription
    subscription = fresh
    if subscription.activation_welcome_message_id is not None:
        return subscription

    embed = render_embed(
        "network_activation_welcome",
        author_icon_url=_bot_author_icon_url(bot),
        network_display_name=network.display_name,
        network_key=network.key,
        client_server_name=client.server_name,
    )
    try:
        message = await subscribe_channel.send(embed=embed, silent=True)
    except discord.HTTPException:
        logger.warning(
            "Could not post server connected message to subscribe channel",
            extra={
                "subscription_id": subscription.id,
                "subscribe_channel_id": subscription.subscribe_channel_id,
            },
        )
        return subscription

    await _publish_announcement(message)

    updated = await context.store.clients.update_activation_welcome_message_id(
        subscription.id,
        message.id,
    )
    await _broadcast_network_member_welcome(
        bot,
        context,
        guild,
        client=client,
        subscription=subscription,
        network=network,
    )
    return updated


async def sync_subscription_setup(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    *,
    client: Client,
    subscription: ClientSubscription,
    network: Network | None,
    setup_mode: SetupMode = "create",
    view_registry: ViewRegistry,
) -> SubscriptionSetupState:
    """Refresh setup stickies, moderation card, and profile for one subscription."""
    from bot.clients.profile_sync import (
        post_subscription_moderation_embed,
        refresh_client_profile_message,
    )

    allow_create = setup_mode == "create"
    bot_user_id = bot.user.id if bot.user is not None else 0
    network_active = network is not None and network.enabled
    from bot.hub.announcements import is_hub_announcements_client

    hub_client = is_hub_announcements_client(client, bot.settings)
    state = await resolve_setup_state(
        guild,
        subscription,
        network_active=network_active,
    )

    if network is not None and network_active and bot_user_id and not hub_client:
        publish_channel = await fetch_publish_channel(guild, subscription)
        subscribe_channel = await fetch_subscribe_channel(guild, subscription)
        if isinstance(publish_channel, discord.TextChannel):
            subscription = await _sync_publish_setup_sticky(
                guild,
                subscription,
                publish_channel=publish_channel,
                context=context,
                bot_user_id=bot_user_id,
                configured=state.publish_configured,
                allow_create=allow_create
                or subscription.publish_setup_message_id is None,
            )
            state = await resolve_setup_state(
                guild,
                subscription,
                network_active=network_active,
            )
        if subscribe_channel is not None:
            subscription = await _sync_subscribe_setup_sticky(
                guild,
                subscription,
                subscribe_channel=subscribe_channel,
                context=context,
                network=network,
                bot_user_id=bot_user_id,
                confirmed=state.subscribe_confirmed,
                allow_create=allow_create
                or subscription.subscribe_setup_message_id is None,
                view_registry=view_registry,
            )
            state = await resolve_setup_state(
                guild,
                subscription,
                network_active=network_active,
            )
            subscription = await _maybe_post_activation_welcome(
                bot,
                subscription,
                subscribe_channel=subscribe_channel,
                context=context,
                guild=guild,
                network=network,
                client=client,
                setup_state=state,
            )

        await post_subscription_moderation_embed(
            bot,
            context,
            guild,
            client=client,
            network=network,
            subscription=subscription,
            setup_state=state,
            setup_mode=setup_mode,
            view_registry=view_registry,
        )

    await refresh_client_profile_message(
        bot,
        context,
        guild,
        client,
        view_registry=view_registry,
    )
    return state


async def sync_all_subscription_setups(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    *,
    view_registry: ViewRegistry,
) -> int:
    """Ensure setup stickies and moderation cards exist for every subscription."""
    synced = 0
    for client in await context.store.clients.list_all():
        if client.guild_id != guild.id:
            continue
        subscriptions = await context.store.clients.list_subscriptions_by_client(client.id)
        for subscription in subscriptions:
            network = None
            if subscription.network_id is not None:
                network = await context.store.networks.get_by_id(subscription.network_id)
            if network is None and subscription.network_key:
                network = await context.store.networks.get_by_key(subscription.network_key)
            await sync_subscription_setup(
                bot,
                context,
                guild,
                client=client,
                subscription=subscription,
                network=network,
                setup_mode="reconcile",
                view_registry=view_registry,
            )
            synced += 1
    return synced


async def sync_subscription_setup_by_publish_channel(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    publish_channel_id: int,
    *,
    view_registry: ViewRegistry,
) -> None:
    subscription = await context.store.clients.get_subscription_by_publish_channel(
        publish_channel_id,
    )
    if subscription is None:
        return
    client = await context.store.clients.get_by_id(subscription.client_id)
    if client is None:
        return
    network = (
        await context.store.networks.get_by_id(subscription.network_id)
        if subscription.network_id is not None
        else None
    )
    await sync_subscription_setup(
        bot,
        context,
        guild,
        client=client,
        subscription=subscription,
        network=network,
        setup_mode="reconcile",
        view_registry=view_registry,
    )
