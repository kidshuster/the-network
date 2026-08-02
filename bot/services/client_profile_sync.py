from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.domain.network import Network
from bot.services.client_profile_post import build_client_profile_embed
from bot.ui.network_views import NetworkProfileView, SubscriptionModerationView

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)


async def refresh_client_profile_message(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    client: Client,
) -> None:
    channel = guild.get_channel(client.profile_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    subscriptions = await context.client_repo.list_subscriptions_by_client(client.id)
    network_entries: list[tuple[str, str]] = []
    subscribed_keys: set[str] = set()
    for sub in subscriptions:
        key = sub.network_key
        network = (
            await context.network_repo.get_by_id(sub.network_id)
            if sub.network_id is not None
            else None
        )
        if not key and network is not None:
            key = network.key
        if not key:
            continue
        subscribed_keys.add(key)
        if network is not None and network.enabled:
            status = "Active"
        else:
            status = "Disabled"
        network_entries.append((key, status))

    all_networks = await context.network_repo.list_all()
    view = NetworkProfileView(
        bot,
        client.id,
        [n.key for n in all_networks],
        subscribed_keys=subscribed_keys,
    )
    bot.add_view(view)

    embed = build_client_profile_embed(
        server_name=client.server_name,
        display_name=client.display_name,
        enabled=client.enabled,
        emoji_id=client.emoji_id,
        subscribed_networks=tuple(network_entries),
    )

    try:
        message = await channel.fetch_message(client.profile_message_id)
        await message.edit(embed=embed, view=view)
    except discord.HTTPException:
        message = await channel.send(embed=embed, view=view, silent=True)
        await context.client_repo.update_profile_message_id(client.id, message.id)


async def refresh_all_client_profiles(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
) -> int:
    updated = 0
    for client in await context.client_repo.list_all():
        if client.guild_id != guild.id:
            continue
        await refresh_client_profile_message(bot, context, guild, client)
        updated += 1
    return updated


def build_moderation_embed(
    *,
    network_display_name: str,
    network_key: str,
    client_server_name: str,
) -> discord.Embed:
    from bot.messages import render_embed
    from bot.services.channel_names import slugify_client_name

    client_slug = slugify_client_name(client_server_name)
    return render_embed(
        "subscription_moderation",
        network_display_name=network_display_name,
        network_key=network_key,
        client_slug=client_slug,
    )


async def post_subscription_moderation_embed(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    *,
    client: Client,
    network: Network,
    subscription: ClientSubscription,
) -> None:
    channel = guild.get_channel(client.profile_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    if subscription.moderation_message_id is not None:
        try:
            prior = await channel.fetch_message(subscription.moderation_message_id)
            await prior.delete()
        except discord.HTTPException:
            pass

    view = SubscriptionModerationView(bot, subscription.id, network.key)
    bot.add_view(view)
    embed = build_moderation_embed(
        network_display_name=network.display_name,
        network_key=network.key,
        client_server_name=client.server_name,
    )
    try:
        message = await channel.send(embed=embed, view=view, silent=True)
        await context.client_repo.update_moderation_message_id(
            subscription.id,
            message.id,
        )
    except discord.HTTPException:
        logger.warning(
            "Could not post subscription moderation embed",
            extra={"subscription_id": subscription.id},
        )
