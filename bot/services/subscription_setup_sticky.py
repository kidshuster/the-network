from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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


async def _delete_setup_message(
    guild: discord.Guild,
    channel_id: int,
    message_id: int | None,
) -> None:
    if message_id is None:
        return
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
    except discord.HTTPException:
        pass


async def _sync_publish_setup_sticky(
    guild: discord.Guild,
    subscription: ClientSubscription,
    *,
    publish_channel: discord.TextChannel,
    context: BotContext,
    configured: bool,
) -> ClientSubscription:
    if configured:
        await _delete_setup_message(
            guild,
            publish_channel.id,
            subscription.publish_setup_message_id,
        )
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
    if subscription.publish_setup_message_id is not None:
        try:
            message = await publish_channel.fetch_message(
                subscription.publish_setup_message_id,
            )
            await message.edit(embed=embed)
            return subscription
        except discord.HTTPException:
            pass

    message = await publish_channel.send(embed=embed, silent=True)
    return await context.client_repo.update_publish_setup_message_id(
        subscription.id,
        message.id,
    )


async def _sync_subscribe_setup_sticky(
    guild: discord.Guild,
    subscription: ClientSubscription,
    *,
    subscribe_channel: discord.abc.GuildChannel,
    context: BotContext,
    confirmed: bool,
) -> ClientSubscription:
    if confirmed:
        await _delete_setup_message(
            guild,
            subscribe_channel.id,
            subscription.subscribe_setup_message_id,
        )
        if subscription.subscribe_setup_message_id is not None:
            return await context.client_repo.update_subscribe_setup_message_id(
                subscription.id,
                None,
            )
        return subscription

    if not isinstance(subscribe_channel, discord.TextChannel):
        return subscription

    embed = render_embed(
        "subscribe_setup_instructions",
        subscribe_mention=subscribe_channel.mention,
    )
    if subscription.subscribe_setup_message_id is not None:
        try:
            message = await subscribe_channel.fetch_message(
                subscription.subscribe_setup_message_id,
            )
            await message.edit(embed=embed)
            return subscription
        except discord.HTTPException:
            pass

    message = await subscribe_channel.send(embed=embed, silent=True)
    return await context.client_repo.update_subscribe_setup_message_id(
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
) -> SubscriptionSetupState:
    """Refresh setup stickies, moderation card, and profile for one subscription."""
    from bot.services.client_profile_sync import (
        post_subscription_moderation_embed,
        refresh_client_profile_message,
    )

    network_active = network is not None and network.enabled
    state = await resolve_setup_state(
        guild,
        subscription,
        network_active=network_active,
    )

    if network is not None and network_active:
        publish_channel = guild.get_channel(subscription.publish_channel_id)
        subscribe_channel = guild.get_channel(subscription.subscribe_channel_id)
        if isinstance(publish_channel, discord.TextChannel):
            subscription = await _sync_publish_setup_sticky(
                guild,
                subscription,
                publish_channel=publish_channel,
                context=context,
                configured=state.publish_configured,
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
                confirmed=state.subscribe_confirmed,
            )

        await post_subscription_moderation_embed(
            bot,
            context,
            guild,
            client=client,
            network=network,
            subscription=subscription,
            setup_state=state,
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
    )
