"""Subscription-facing recipes (webhook sync, blacklist)."""

from __future__ import annotations

from typing import Any

import discord

from bot.contracts.recipes import RecipeContext, recipe


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
    client: Any = None,
) -> int:
    from bot.features.widgets.guards import require_client_member, require_hub_guild

    if guild is not None:
        require_hub_guild(recipe_context.bot, guild)
        if member is not None and client is not None:
            require_client_member(
                guild,
                member,
                client,
                popup="client_role_required_subscribe",
                allow_non_member=True,
            )
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


@recipe("subscription.create")
async def create_subscription(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    client: Any,
    network: Any,
    view_registry: Any,
    member: discord.abc.User | None = None,
) -> Any:
    from bot.features.channels.stickies.subscription import sync_subscription_setup
    from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message
    from bot.features.recipes.hub.clients.subscription import subscribe_client
    from bot.features.widgets.guards import require_client_member, require_hub_guild

    require_hub_guild(recipe_context.bot, guild)
    if member is not None:
        require_client_member(
            guild,
            member,
            client,
            popup="client_role_required_subscribe",
            allow_non_member=True,
        )
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
    client: Any,
    subscription: Any,
    network_key: str,
    view_registry: Any,
    member: discord.abc.User | None = None,
) -> Any:
    from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message
    from bot.features.recipes.hub.clients.subscription import unsubscribe_client
    from bot.features.widgets.guards import require_client_member, require_hub_guild

    require_hub_guild(recipe_context.bot, guild)
    if member is not None:
        require_client_member(
            guild,
            member,
            client,
            popup="client_role_required_subscribe",
            allow_non_member=True,
        )
    result = await unsubscribe_client(
        guild,
        bot_member,
        client=client,
        subscription=subscription,
        network_key=network_key,
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
    client: Any,
    subscription: Any,
    network: Any,
    view_registry: Any,
    member: discord.abc.User | None = None,
) -> Any:
    from bot.features.channels.stickies.subscription import sync_subscription_setup
    from bot.features.widgets.guards import require_client_member, require_hub_guild

    require_hub_guild(recipe_context.bot, guild)
    if member is not None:
        require_client_member(
            guild,
            member,
            client,
            popup="client_role_required_subscribe",
            allow_non_member=True,
        )
    updated = await recipe_context.core.store.clients.set_subscribe_confirmed(
        subscription.id,
        True,
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

