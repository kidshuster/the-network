from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import discord

from bot.clients.profile_post import build_client_profile_embed
from bot.clients.resources import (
    fetch_publish_channel,
    fetch_subscribe_channel,
    resolve_client_profile_channel,
)
from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.domain.network import Network
from bot.stickies.subscription_setup import (
    SubscriptionSetupState,
    resolve_setup_state,
)
from bot.ui.view_registry import ViewRegistry

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

SetupMode = Literal["create", "reconcile"]


async def _network_link_status_for_subscription(
    guild: discord.Guild,
    subscription: ClientSubscription,
    *,
    network: Network | None,
) -> str:
    network_active = network is not None and network.enabled
    if not network_active:
        return "Disabled"
    state = await resolve_setup_state(
        guild,
        subscription,
        network_active=network_active,
    )
    return state.link_status


async def refresh_client_profile_message(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    client: Client,
    *,
    view_registry: ViewRegistry,
) -> None:
    channel = await resolve_client_profile_channel(guild, client)
    if channel is None:
        return

    subscriptions = await context.store.clients.list_subscriptions_by_client(client.id)
    network_entries: list[tuple[str, str]] = []
    subscribed_keys: set[str] = set()
    for sub in subscriptions:
        key = sub.network_key
        network = (
            await context.store.networks.get_by_id(sub.network_id)
            if sub.network_id is not None
            else None
        )
        if not key and network is not None:
            key = network.key
        if not key:
            continue
        subscribed_keys.add(key)
        status = await _network_link_status_for_subscription(
            guild,
            sub,
            network=network,
        )
        network_entries.append((key, status))

    all_networks = await context.store.networks.list_all()
    network_keys = [n.key for n in all_networks]
    view = view_registry.register_client_profile_view(
        client.id,
        network_keys,
        subscribed_keys=subscribed_keys,
        timecode_enabled=client.timecode_enabled,
    )

    embed = build_client_profile_embed(
        server_name=client.server_name,
        display_name=client.display_name,
        enabled=client.enabled,
        emoji_id=client.emoji_id,
        timecode_enabled=client.timecode_enabled,
        subscribed_networks=tuple(network_entries),
    )

    try:
        message = await channel.fetch_message(client.profile_message_id)
        await message.edit(embed=embed, view=view)
    except discord.HTTPException:
        message = await channel.send(embed=embed, view=view, silent=True)
        await context.store.clients.update_profile_message_id(client.id, message.id)


async def refresh_all_client_profiles(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    *,
    view_registry: ViewRegistry,
) -> int:
    updated = 0
    for client in await context.store.clients.list_all():
        if client.guild_id != guild.id:
            continue
        await refresh_client_profile_message(
            bot,
            context,
            guild,
            client,
            view_registry=view_registry,
        )
        updated += 1
    return updated


def _setup_description(
    network_key: str,
    setup_state: SubscriptionSetupState,
) -> str:
    needs_publish = not setup_state.publish_configured
    needs_subscribe = not setup_state.subscribe_confirmed
    if needs_publish and needs_subscribe:
        return f"Finish connecting **`{network_key}`** before relays can flow."
    if needs_publish:
        return (
            f"Connect your **publish** channel for **`{network_key}`** "
            "to finish setup."
        )
    if needs_subscribe:
        return (
            f"Connect your **subscribe** channel for **`{network_key}`** "
            "to finish setup."
        )
    return f"**`{network_key}`** is connected."


def build_moderation_embed(
    *,
    network_display_name: str,
    network_key: str,
    client_server_name: str,
    setup_state: SubscriptionSetupState | None = None,
    publish_mention: str = "",
    subscribe_mention: str = "",
) -> discord.Embed:
    from bot.clients.names import slugify_client_name
    from bot.messages import render_embed

    client_slug = slugify_client_name(client_server_name)
    if setup_state is not None and not setup_state.fully_configured:
        return render_embed(
            "subscription_moderation_setup",
            network_display_name=network_display_name,
            network_key=network_key,
            publish_mention=publish_mention,
            subscribe_mention=subscribe_mention,
            setup_description=_setup_description(network_key, setup_state),
            needs_publish="1" if not setup_state.publish_configured else "",
            needs_subscribe="1" if not setup_state.subscribe_confirmed else "",
        )
    return render_embed(
        "subscription_moderation",
        network_display_name=network_display_name,
        network_key=network_key,
        client_slug=client_slug,
    )


def _moderation_view(
    view_registry: ViewRegistry,
    subscription: ClientSubscription,
    network: Network,
    setup_state: SubscriptionSetupState,
) -> discord.ui.View:
    return view_registry.register_subscription_moderation_view(
        subscription,
        network,
        setup_state,
    )


async def post_subscription_moderation_embed(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    *,
    client: Client,
    network: Network,
    subscription: ClientSubscription,
    setup_state: SubscriptionSetupState | None = None,
    setup_mode: SetupMode = "create",
    view_registry: ViewRegistry,
) -> None:
    channel = await resolve_client_profile_channel(guild, client)
    if channel is None:
        return

    if setup_state is None:
        setup_state = await resolve_setup_state(
            guild,
            subscription,
            network_active=network.enabled,
        )

    if setup_mode == "reconcile" and setup_state.fully_configured:
        return

    publish_channel = await fetch_publish_channel(guild, subscription)
    subscribe_channel = await fetch_subscribe_channel(guild, subscription)
    publish_mention = publish_channel.mention if publish_channel is not None else "#publish"
    subscribe_mention = (
        subscribe_channel.mention if subscribe_channel is not None else "#subscribe"
    )

    view = _moderation_view(view_registry, subscription, network, setup_state)
    embed = build_moderation_embed(
        network_display_name=network.display_name,
        network_key=network.key,
        client_server_name=client.server_name,
        setup_state=setup_state,
        publish_mention=publish_mention,
        subscribe_mention=subscribe_mention,
    )

    if subscription.moderation_message_id is not None:
        try:
            message = await channel.fetch_message(subscription.moderation_message_id)
            await message.edit(embed=embed, view=view)
            return
        except discord.HTTPException:
            if setup_mode == "reconcile":
                return

    if setup_mode == "reconcile":
        return

    try:
        message = await channel.send(embed=embed, view=view, silent=True)
        await context.store.clients.update_moderation_message_id(
            subscription.id,
            message.id,
        )
    except discord.HTTPException:
        logger.warning(
            "Could not post subscription moderation embed",
            extra={"subscription_id": subscription.id},
        )
