"""Subscription-facing recipes (webhook sync, blacklist)."""

from __future__ import annotations

from typing import Any

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.contracts.widgets import OpenEphemeralView, SelectOptionSpec, SelectSpec, recipe_handler
from bot.core.templates import render_text
from bot.errors import UserFacingError
from bot.features.widgets.guards import require_client_member, require_hub_guild


def _fail(code: str, **values: Any) -> UserFacingError:
    return UserFacingError(render_text(code, **values), code=code)


async def _resolve(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    member: discord.abc.User | None,
    subscription_id: int | None = None,
    client_id: int | None = None,
    network_key: str | None = None,
    popup: str = "client_role_required_subscribe",
) -> tuple[Any, Any, Any | None]:
    require_hub_guild(recipe_context.bot, guild)
    repo = recipe_context.core.store.clients
    networks = recipe_context.core.store.networks
    subscription = network = None
    client = None
    if subscription_id is not None:
        subscription = await repo.get_subscription_by_id(subscription_id)
        if subscription is None:
            raise _fail("subscription_not_found")
        client = await repo.get_by_id(subscription.client_id)
        if subscription.network_id is not None:
            network = await networks.get_by_id(subscription.network_id)
    if client is None and client_id is not None:
        client = await repo.get_by_id(client_id)
    if client is None:
        raise _fail("client_not_found")
    if member is not None:
        require_client_member(guild, member, client, popup=popup, allow_non_member=True)
    if network is None and network_key is not None:
        network = await networks.get_by_key(network_key)
        if network is None:
            raise _fail("network_not_found", network_key=network_key)
    return client, subscription, network


@recipe("subscription.webhook_updated")
async def webhook_updated(
    recipe_context: RecipeContext, *, channel: discord.abc.GuildChannel
) -> Any:
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
        view_registry=recipe_context.bot.make_view_registry(),
    )


@recipe("blacklist.replace")
async def replace_blacklist(
    recipe_context: RecipeContext,
    *,
    subscription_id: int,
    selected_client_ids: list[str] | tuple[str, ...] | set[str],
    guild: discord.Guild | None = None,
    member: discord.abc.User | None = None,
) -> int:
    if guild is not None:
        await _resolve(
            recipe_context,
            guild=guild,
            member=member,
            subscription_id=subscription_id,
            popup="client_role_required_blacklist",
        )
    repo = recipe_context.core.store.clients
    subscription = await repo.get_subscription_by_id(subscription_id)
    if subscription is None or subscription.network_id is None:
        raise _fail("subscription_not_found")
    allowed = {
        item.client_id
        for item in await repo.list_subscriptions_by_network(subscription.network_id)
        if item.client_id != subscription.client_id
    }
    selected = {int(value) for value in selected_client_ids} & allowed
    current = set(await repo.list_blacklisted_client_ids(subscription_id)) & allowed
    for peer_id in selected - current:
        await repo.add_blacklist(subscription_id, peer_id)
    for peer_id in current - selected:
        await repo.remove_blacklist(subscription_id, peer_id)
    return len(selected)


@recipe("subscription.create")
async def create_subscription(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    view_registry: Any,
    client_id: int,
    network_key: str,
    member: discord.abc.User | None = None,
) -> Any:
    from bot.features.channels.stickies.subscription import sync_subscription_setup
    from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message
    from bot.features.recipes.hub.clients.subscription import subscribe_client

    client, _, network = await _resolve(
        recipe_context,
        guild=guild,
        member=member,
        client_id=client_id,
        network_key=network_key,
    )
    assert network is not None
    result = await subscribe_client(
        guild,
        bot_member,
        client=client,
        network_id=network.id,
        network_key=network.key,
        client_repo=recipe_context.core.store.clients,
        network_repo=recipe_context.core.store.networks,
        access_role_name=recipe_context.bot.settings.network_access_role_name,
    )
    if not result.success or result.subscription is None:
        return result
    await recipe_context.core.refresh_projections()
    if result.created:
        await sync_subscription_setup(
            recipe_context.bot,
            recipe_context.core,
            guild,
            client=client,
            subscription=result.subscription,
            network=network,
            view_registry=view_registry,
        )
    else:
        await refresh_client_profile_message(
            recipe_context.bot,
            recipe_context.core,
            guild,
            client,
            view_registry=view_registry,
        )
    return result


@recipe("subscription.leave")
async def leave_subscription(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    view_registry: Any,
    subscription_id: int,
    network_key: str = "",
    member: discord.abc.User | None = None,
) -> Any:
    from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message
    from bot.features.recipes.hub.clients.subscription import unsubscribe_client

    client, subscription, network = await _resolve(
        recipe_context,
        guild=guild,
        member=member,
        subscription_id=subscription_id,
        network_key=network_key or None,
        popup="client_role_required_leave",
    )
    if subscription is None:
        raise _fail("subscription_not_found")
    result = await unsubscribe_client(
        guild,
        bot_member,
        client=client,
        subscription=subscription,
        network_key=(network.key if network is not None else network_key),
        client_repo=recipe_context.core.store.clients,
        network_repo=recipe_context.core.store.networks,
    )
    if not result.success:
        return result
    await recipe_context.core.refresh_projections()
    await refresh_client_profile_message(
        recipe_context.bot,
        recipe_context.core,
        guild,
        client,
        view_registry=view_registry,
    )
    return result


@recipe("subscription.confirm_connected")
async def confirm_subscription_connected(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    view_registry: Any,
    subscription_id: int,
    network_key: str | None = None,
    member: discord.abc.User | None = None,
) -> Any:
    from bot.features.channels.stickies.subscription import sync_subscription_setup

    client, subscription, network = await _resolve(
        recipe_context,
        guild=guild,
        member=member,
        subscription_id=subscription_id,
        network_key=network_key,
    )
    if subscription is None or network is None:
        raise _fail("subscription_not_found")
    updated = await recipe_context.core.store.clients.set_subscribe_confirmed(
        subscription.id, True
    )
    await sync_subscription_setup(
        recipe_context.bot,
        recipe_context.core,
        guild,
        client=client,
        subscription=updated,
        network=network,
        view_registry=view_registry,
    )
    return updated


@recipe("subscription.blacklist.open")
async def open_blacklist(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    subscription_id: int,
    member: discord.abc.User | None = None,
) -> OpenEphemeralView:
    _client, subscription, _network = await _resolve(
        recipe_context,
        guild=guild,
        member=member,
        subscription_id=subscription_id,
        popup="client_role_required_blacklist",
    )
    if subscription is None or subscription.network_id is None:
        raise _fail("subscription_not_found")
    repo = recipe_context.core.store.clients
    peers = [
        item
        for item in await repo.list_subscriptions_by_network(subscription.network_id)
        if item.client_id != subscription.client_id
    ]
    if not peers:
        raise _fail("no_blacklist_targets")
    current = set(await repo.list_blacklisted_client_ids(subscription_id))
    options = [
        SelectOptionSpec(
            label=peer_client.display_name[:100],
            value=str(peer_client.id),
            default=peer_client.id in current,
        )
        for peer in peers[:25]
        if (peer_client := await repo.get_by_id(peer.client_id)) is not None
    ]
    if not options:
        raise _fail("no_blacklist_targets")
    return OpenEphemeralView(
        template_id="blacklist_select",
        content=render_text("blacklist_select_prompt"),
        slots={
            "blacklist": (
                SelectSpec(
                    tag="select",
                    placeholder="Blacklist clients…",
                    options=tuple(options),
                    handler=recipe_handler(
                        "blacklist.replace", subscription_id=subscription_id
                    ),
                    min_values=0,
                    max_values=max(len(options), 1),
                ),
            )
        },
    )
