from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import discord

from bot.core.clients.resources import resolve_client_category
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.network import Network
from bot.core.views import ViewRegistry
from bot.features.channels.layout.loader import load_layout
from bot.features.channels.stickies.subscription import sync_subscription_setup
from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message
from bot.features.recipes.hub.clients.rectification import rectify_client_permissions
from bot.features.recipes.hub.clients.subscription import (
    reorder_client_category_channels,
    resync_subscriptions_for_network,
    sync_client_channel_names,
)
from bot.features.recipes.hub.result import GuildInitResult

logger = logging.getLogger(__name__)


async def _run_reconnect_step(name: str, action: Callable[[], Awaitable[object]]) -> None:
    await action()


async def _finish_client_reconnect(
    guild: discord.Guild,
    bot: Any,
    context: Any,
    bot_member: discord.Member,
    client: Client,
    *,
    view_registry: ViewRegistry,
) -> None:
    await _run_reconnect_step(
        "sync channel names",
        lambda: sync_client_channel_names(
            guild,
            bot_member,
            client=client,
            client_repo=context.store.clients,
            network_repo=context.store.networks,
        ),
    )

    subscriptions = await context.store.clients.list_subscriptions_by_client(client.id)
    for subscription in subscriptions:
        network_id = subscription.network_id
        if network_id is None:
            continue
        network = await context.store.networks.get_by_id(network_id)
        if network is None:
            continue

        async def _sync_setup(
            sub: ClientSubscription = subscription,
            net: Network = network,
        ) -> None:
            await sync_subscription_setup(
                bot,
                context,
                guild,
                client=client,
                subscription=sub,
                network=net,
                setup_mode="reconcile",
                view_registry=view_registry,
            )

        await _run_reconnect_step(
            f"sync subscription setup for {network.key}",
            _sync_setup,
        )

    category = await resolve_client_category(guild, client)
    if category is not None:
        await _run_reconnect_step(
            "reorder client category channels",
            lambda: reorder_client_category_channels(
                category,
                client=client,
                client_repo=context.store.clients,
                network_repo=context.store.networks,
            ),
        )

    all_networks = await context.store.networks.list_all()
    view_registry.register_client_profile_for_client(
        client,
        [network.key for network in all_networks],
    )
    await _run_reconnect_step(
        "refresh client profile message",
        lambda: refresh_client_profile_message(
            bot,
            context,
            guild,
            client,
            view_registry=view_registry,
        ),
    )


async def _client_category_position(
    guild: discord.Guild,
    context: Any,
    client: Client,
) -> int:
    from bot.core.channels.order import next_trailing_position

    hub_count = len(load_layout().layout.categories)
    guild_clients = [
        item
        for item in await context.store.clients.list_all()
        if item.guild_id == guild.id
    ]
    guild_clients.sort(key=lambda item: item.server_name.casefold())
    for index, item in enumerate(guild_clients):
        if item.id == client.id:
            return next_trailing_position(leading_count=hub_count, trailing_count=index)
    return next_trailing_position(leading_count=hub_count, trailing_count=len(guild_clients))


async def rectify_client_on_init(
    guild: discord.Guild,
    bot: Any,
    context: Any,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    client: Client,
    *,
    result: GuildInitResult,
    access_role_name: str | None = None,
    view_registry: ViewRegistry,
) -> bool:
    """Rectify one client layout and finish name/sticky/profile sync. Returns True if finished."""
    role_name = access_role_name or bot.settings.network_access_role_name
    category_position = await _client_category_position(guild, context, client)
    rectified = await rectify_client_permissions(
        guild,
        bot_member,
        context,
        client,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        access_role_name=role_name,
        category_position=category_position,
    )
    result.rectifications.extend(rectified.rectification_notes())
    result.rectification_skipped.extend(rectified.skip_notes())
    result.rectification_failures.extend(rectified.failure_notes())

    if rectified.skipped and not rectified.synced:
        return False

    category = await resolve_client_category(guild, client)
    if category is None:
        return False

    try:
        await _finish_client_reconnect(
            guild,
            bot,
            context,
            bot_member,
            client,
            view_registry=view_registry,
        )
    except discord.HTTPException as exc:
        result.rectification_failures.append(
            f"**{client.server_name}**: could not finish reconnect ({exc})"
        )
        logger.warning(
            "Client reconnect failed",
            extra={"client_id": client.id, "error": str(exc)},
        )
        return False
    return True


async def resync_networks_on_init(
    guild: discord.Guild,
    bot: Any,
    context: Any,
    *,
    result: GuildInitResult,
    access_role_name: str | None = None,
    view_registry: ViewRegistry,
) -> None:
    role_name = access_role_name or bot.settings.network_access_role_name
    for network in await context.store.networks.list_all():
        relinked = await resync_subscriptions_for_network(
            guild,
            bot,
            context,
            network,
            access_role_name=role_name,
            view_registry=view_registry,
        )
        if relinked:
            result.rectifications.append(
                f"Relinked {relinked} subscription(s) for network `{network.key}`."
            )


async def reconnect_clients_on_init(
    guild: discord.Guild,
    bot: Any,
    context: Any,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    clients: list[Client],
    *,
    result: GuildInitResult,
    access_role_name: str | None = None,
    view_registry: ViewRegistry,
) -> None:
    role_name = access_role_name or bot.settings.network_access_role_name
    guild_clients = [client for client in clients if client.guild_id == guild.id]
    if not guild_clients:
        result.rectifications.append(
            "Client profiles: none registered — skipped permission rectification."
        )
        return

    reconnected = 0
    for client in guild_clients:
        finished = await rectify_client_on_init(
            guild,
            bot,
            context,
            bot_member,
            access_role,
            human_moderator_role,
            client,
            result=result,
            access_role_name=role_name,
            view_registry=view_registry,
        )
        if finished:
            reconnected += 1

    await resync_networks_on_init(
        guild,
        bot,
        context,
        result=result,
        access_role_name=role_name,
        view_registry=view_registry,
    )

    if reconnected:
        result.rectifications.append(
            f"Verified and refreshed {reconnected} client profile card(s)."
        )

