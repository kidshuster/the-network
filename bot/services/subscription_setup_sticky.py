from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import discord

from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.domain.network import Network
from bot.messages import render_embed
from bot.services.subscription_setup import SubscriptionSetupState, resolve_setup_state

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

SetupMode = Literal["create", "reconcile"]

_PUBLISH_SETUP_FOOTER = "publish setup"
_SUBSCRIBE_SETUP_FOOTER = "subscribe setup"
_SETUP_HISTORY_LIMIT = 50


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


async def _find_setup_sticky_by_scan(
    channel: discord.abc.GuildChannel,
    *,
    bot_user_id: int,
    footer_marker: str,
) -> discord.Message | None:
    if not hasattr(channel, "history"):
        return None
    marker = footer_marker.casefold()
    try:
        async for message in channel.history(limit=_SETUP_HISTORY_LIMIT):
            if message.author.id != bot_user_id or not message.embeds:
                continue
            footer = (message.embeds[0].footer.text or "").casefold()
            if marker in footer:
                return message
    except discord.HTTPException:
        return None
    return None


async def _resolve_setup_sticky_message(
    channel: discord.abc.GuildChannel,
    *,
    bot_user_id: int,
    message_id: int | None,
    footer_marker: str,
) -> discord.Message | None:
    if message_id is not None and hasattr(channel, "fetch_message"):
        try:
            return await channel.fetch_message(message_id)
        except discord.HTTPException:
            pass
    return await _find_setup_sticky_by_scan(
        channel,
        bot_user_id=bot_user_id,
        footer_marker=footer_marker,
    )


def _subscribe_setup_view(
    bot: NetworkRelayBot,
    subscription: ClientSubscription,
    network: Network,
) -> discord.ui.View:
    from bot.ui.network_views import SubscribeSetupView

    view = SubscribeSetupView(bot, subscription.id, network.key)
    bot.add_view(view)
    return view


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
    if configured:
        message = await _resolve_setup_sticky_message(
            publish_channel,
            bot_user_id=bot_user_id,
            message_id=subscription.publish_setup_message_id,
            footer_marker=_PUBLISH_SETUP_FOOTER,
        )
        if message is not None:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
        if subscription.publish_setup_message_id is not None:
            return await context.client_repo.update_publish_setup_message_id(
                subscription.id,
                None,
            )
        return subscription

    embed = render_embed(
        "publish_setup_instructions",
        publish_mention=publish_channel.mention,
    )
    message = await _resolve_setup_sticky_message(
        publish_channel,
        bot_user_id=bot_user_id,
        message_id=subscription.publish_setup_message_id,
        footer_marker=_PUBLISH_SETUP_FOOTER,
    )
    if message is not None:
        try:
            await message.edit(embed=embed)
            if subscription.publish_setup_message_id != message.id:
                return await context.client_repo.update_publish_setup_message_id(
                    subscription.id,
                    message.id,
                )
            return subscription
        except discord.HTTPException:
            logger.warning(
                "Could not refresh publish setup sticky",
                extra={"subscription_id": subscription.id, "message_id": message.id},
            )

    if not allow_create:
        return subscription

    message = await publish_channel.send(embed=embed, silent=True)
    return await context.client_repo.update_publish_setup_message_id(
        subscription.id,
        message.id,
    )


async def _sync_subscribe_setup_sticky(
    bot: NetworkRelayBot,
    guild: discord.Guild,
    subscription: ClientSubscription,
    *,
    subscribe_channel: discord.abc.GuildChannel,
    context: BotContext,
    network: Network,
    bot_user_id: int,
    confirmed: bool,
    allow_create: bool,
) -> ClientSubscription:
    if confirmed:
        message = await _resolve_setup_sticky_message(
            subscribe_channel,
            bot_user_id=bot_user_id,
            message_id=subscription.subscribe_setup_message_id,
            footer_marker=_SUBSCRIBE_SETUP_FOOTER,
        )
        if message is not None:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
        if subscription.subscribe_setup_message_id is not None:
            return await context.client_repo.update_subscribe_setup_message_id(
                subscription.id,
                None,
            )
        return subscription

    if not _supports_setup_sticky(subscribe_channel):
        return subscription

    embed = render_embed(
        "subscribe_setup_instructions",
        subscribe_mention=subscribe_channel.mention,
    )
    view = _subscribe_setup_view(bot, subscription, network)
    message = await _resolve_setup_sticky_message(
        subscribe_channel,
        bot_user_id=bot_user_id,
        message_id=subscription.subscribe_setup_message_id,
        footer_marker=_SUBSCRIBE_SETUP_FOOTER,
    )
    if message is not None:
        try:
            await message.edit(embed=embed, view=view)
            if subscription.subscribe_setup_message_id != message.id:
                return await context.client_repo.update_subscribe_setup_message_id(
                    subscription.id,
                    message.id,
                )
            return subscription
        except discord.HTTPException:
            logger.warning(
                "Could not refresh subscribe setup sticky",
                extra={"subscription_id": subscription.id, "message_id": message.id},
            )

    if not allow_create:
        return subscription

    message = await subscribe_channel.send(embed=embed, view=view, silent=True)
    return await context.client_repo.update_subscribe_setup_message_id(
        subscription.id,
        message.id,
    )


async def _maybe_post_activation_welcome(
    subscription: ClientSubscription,
    *,
    subscribe_channel: discord.abc.GuildChannel,
    context: BotContext,
    network: Network,
    client: Client,
    setup_state: SubscriptionSetupState,
) -> ClientSubscription:
    """Post a one-time welcome embed to the subscribe feed when a network first activates."""
    if not setup_state.fully_configured:
        return subscription
    if subscription.activation_welcome_message_id is not None:
        return subscription
    if not hasattr(subscribe_channel, "send"):
        return subscription

    embed = render_embed(
        "network_activation_welcome",
        network_display_name=network.display_name,
        network_key=network.key,
        client_server_name=client.server_name,
    )
    try:
        message = await subscribe_channel.send(embed=embed)
    except discord.HTTPException:
        logger.warning(
            "Could not post activation welcome to subscribe channel",
            extra={
                "subscription_id": subscription.id,
                "subscribe_channel_id": subscription.subscribe_channel_id,
            },
        )
        return subscription

    return await context.client_repo.update_activation_welcome_message_id(
        subscription.id,
        message.id,
    )


async def sync_subscription_setup(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    *,
    client: Client,
    subscription: ClientSubscription,
    network: Network | None,
    setup_mode: SetupMode = "create",
) -> SubscriptionSetupState:
    """Refresh setup stickies, moderation card, and profile for one subscription."""
    from bot.services.client_profile_sync import (
        post_subscription_moderation_embed,
        refresh_client_profile_message,
    )

    allow_create = setup_mode == "create"
    bot_user_id = bot.user.id if bot.user is not None else 0
    network_active = network is not None and network.enabled
    state = await resolve_setup_state(
        guild,
        subscription,
        network_active=network_active,
    )

    if network is not None and network_active and bot_user_id:
        publish_channel = guild.get_channel(subscription.publish_channel_id)
        subscribe_channel = guild.get_channel(subscription.subscribe_channel_id)
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
                bot,
                guild,
                subscription,
                subscribe_channel=subscribe_channel,
                context=context,
                network=network,
                bot_user_id=bot_user_id,
                confirmed=state.subscribe_confirmed,
                allow_create=allow_create
                or subscription.subscribe_setup_message_id is None,
            )
            state = await resolve_setup_state(
                guild,
                subscription,
                network_active=network_active,
            )
            subscription = await _maybe_post_activation_welcome(
                subscription,
                subscribe_channel=subscribe_channel,
                context=context,
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
        )

    await refresh_client_profile_message(bot, context, guild, client)
    return state


async def sync_all_subscription_setups(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
) -> int:
    """Ensure setup stickies and moderation cards exist for every subscription."""
    synced = 0
    for client in await context.client_repo.list_all():
        if client.guild_id != guild.id:
            continue
        subscriptions = await context.client_repo.list_subscriptions_by_client(client.id)
        for subscription in subscriptions:
            network = None
            if subscription.network_id is not None:
                network = await context.network_repo.get_by_id(subscription.network_id)
            if network is None and subscription.network_key:
                network = await context.network_repo.get_by_key(subscription.network_key)
            await sync_subscription_setup(
                bot,
                context,
                guild,
                client=client,
                subscription=subscription,
                network=network,
                setup_mode="reconcile",
            )
            synced += 1
    return synced


async def sync_subscription_setup_by_publish_channel(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    publish_channel_id: int,
) -> None:
    subscription = await context.client_repo.get_subscription_by_publish_channel(
        publish_channel_id,
    )
    if subscription is None:
        return
    client = await context.client_repo.get_by_id(subscription.client_id)
    if client is None:
        return
    network = (
        await context.network_repo.get_by_id(subscription.network_id)
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
    )
