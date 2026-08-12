from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import discord

from bot.core.clients.names import (
    build_client_profile_channel_base,
    build_client_publish_channel_base,
    build_client_subscribe_channel_base,
    slugify_client_name,
)
from bot.core.clients.resources import (
    fetch_client_role,
    fetch_publish_channel,
    fetch_subscribe_channel,
    resolve_client_category,
    resolve_client_profile_channel,
    resolve_client_resources,
)
from bot.core.database.store import ClientStore, NetworkStore
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.network import Network
from bot.core.networks.roles import (
    resolve_access_role,
)
from bot.core.views import ViewRegistry
from bot.features.channels.layout import ApplyMode, LayoutContext, apply_layout, compile_client
from bot.features.channels.resolve import resolve_human_moderator_role

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubscribeResult:
    success: bool
    subscription: ClientSubscription | None = None
    created: bool = False
    reactivated: bool = False
    error: str | None = None


@dataclass(frozen=True)
class UnsubscribeResult:
    success: bool
    error: str | None = None


def _match_channel_name(channel: discord.abc.GuildChannel, candidates: Iterable[str]) -> bool:
    name = channel.name.casefold()
    return any(name == candidate.casefold() for candidate in candidates)


def find_network_subscription_channels(
    category: discord.CategoryChannel,
    network_key: str,
    *,
    client: Client,
) -> tuple[discord.TextChannel | None, discord.abc.GuildChannel | None]:
    publish_names = (build_client_publish_channel_base(client.server_name, network_key),)
    subscribe_names = (build_client_subscribe_channel_base(client.server_name, network_key),)

    publish_channel: discord.TextChannel | None = None
    subscribe_channel: discord.abc.GuildChannel | None = None
    for channel in _category_channels(category):
        if (
            publish_channel is None
            and isinstance(channel, discord.TextChannel)
            and _match_channel_name(channel, publish_names)
        ):
            publish_channel = channel
        elif subscribe_channel is None and _match_channel_name(channel, subscribe_names):
            subscribe_channel = channel
    return publish_channel, subscribe_channel


def resolve_subscription_channels_in_category(
    guild: discord.Guild,
    category: discord.CategoryChannel,
    subscription: ClientSubscription,
    network_key: str,
    *,
    client: Client,
) -> tuple[discord.TextChannel | None, discord.abc.GuildChannel | None]:
    publish = guild.get_channel(subscription.publish_channel_id)
    subscribe: discord.abc.GuildChannel | None = guild.get_channel(
        subscription.subscribe_channel_id
    )
    if not isinstance(publish, discord.TextChannel):
        publish = None
    if publish is not None and subscribe is not None:
        return publish, subscribe

    found_publish, found_subscribe = find_network_subscription_channels(
        category,
        network_key,
        client=client,
    )
    if publish is None:
        publish = found_publish
    if subscribe is None:
        subscribe = found_subscribe
    return publish, subscribe


def _operator_role(guild: discord.Guild) -> discord.Role | None:
    try:
        for role in guild.roles:
            if isinstance(role, discord.Role) and role.name == "The Network+":
                return role
    except Exception:
        return None
    return None


def _client_layout_context(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    client_role: discord.Role,
    client: Client,
    network_key: str | None = None,
    reason: str,
) -> LayoutContext:
    return LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access_role,
        moderator_role=human_moderator_role,
        operator_role=_operator_role(guild),
        client_role=client_role,
        server_name=client.server_name,
        slug=slugify_client_name(client.server_name),
        network_key=network_key,
        reason=reason,
    )


async def sync_subscription_channel_permissions(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    client: Client,
    subscription: ClientSubscription,
    access_role_name: str,
) -> None:
    from dataclasses import replace

    access_role = resolve_access_role(guild, role_name=access_role_name)
    human_moderator_role = resolve_human_moderator_role(guild)
    client_role = await fetch_client_role(guild, client)
    if client_role is None:
        return

    publish = await fetch_publish_channel(guild, subscription)
    subscribe = await fetch_subscribe_channel(guild, subscription)
    if publish is None and subscribe is None:
        return

    layout_ctx = _client_layout_context(
        guild,
        bot_member,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        client_role=client_role,
        client=client,
        network_key="sync",
        reason="The Network subscription channel sync",
    )
    resources = []
    for resource in compile_client(
        layout_ctx,
        include_subscribed=True,
        channel_ids={"publish", "subscribe"},
    ):
        if resource.id == "publish" and isinstance(publish, discord.TextChannel):
            resources.append(replace(resource, name=publish.name))
        elif resource.id == "subscribe" and isinstance(subscribe, discord.TextChannel):
            resources.append(replace(resource, name=subscribe.name))
    batch = await apply_layout(layout_ctx, resources, mode=ApplyMode.RECONCILE_ONLY)
    for failure in batch.failures:
        logger.warning("Could not sync subscription channel permissions: %s", failure)


async def sync_client_profile_channel_permissions(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    client: Client,
    access_role_name: str,
) -> None:
    from dataclasses import replace

    access_role = resolve_access_role(guild, role_name=access_role_name)
    human_moderator_role = resolve_human_moderator_role(guild)
    client_role = await fetch_client_role(guild, client)
    if client_role is None:
        return
    profile = await resolve_client_profile_channel(guild, client)
    if profile is None:
        return
    layout_ctx = _client_layout_context(
        guild,
        bot_member,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        client_role=client_role,
        client=client,
        reason="The Network client profile sync",
    )
    resources = [
        replace(resource, name=profile.name) if resource.id == "profile" else resource
        for resource in compile_client(layout_ctx, channel_ids={"profile"})
    ]
    batch = await apply_layout(layout_ctx, resources, mode=ApplyMode.RECONCILE_ONLY)
    if not batch.success:
        logger.warning(
            "Could not sync profile channel permissions",
            extra={"channel_id": profile.id, "failures": batch.failures},
        )


async def subscribe_client(guild: discord.Guild,
    bot_member: discord.Member,
    *,
    client: Client,
    network_id: int,
    network_key: str,
    client_repo: ClientStore,
    network_repo: NetworkStore,
    access_role_name: str,
) -> SubscribeResult:
    existing = await client_repo.get_subscription(client.id, network_id)
    if existing is not None:
        return SubscribeResult(success=True, subscription=existing, created=False)

    access_role = resolve_access_role(guild, role_name=access_role_name)
    human_moderator_role = resolve_human_moderator_role(guild)
    resources = await resolve_client_resources(guild, client)
    if resources.role is None:
        return SubscribeResult(success=False, error="Client role was not found.")

    category = resources.category
    if category is None:
        return SubscribeResult(success=False, error="Client category was not found.")

    client_role = resources.role

    publish_name = build_client_publish_channel_base(client.server_name, network_key)
    subscribe_name = build_client_subscribe_channel_base(client.server_name, network_key)

    publish_channel, subscribe_channel = find_network_subscription_channels(
        category,
        network_key,
        client=client,
    )
    channels_preexisted = publish_channel is not None and subscribe_channel is not None
    newly_created: list[discord.abc.GuildChannel] = []

    if publish_channel is None or subscribe_channel is None:
        try:
            from dataclasses import replace

            layout_ctx = LayoutContext(
                guild=guild,
                bot_member=bot_member,
                access_role=access_role,
                moderator_role=human_moderator_role,
                client_role=client_role,
                server_name=client.server_name,
                slug=slugify_client_name(client.server_name),
                network_key=network_key,
                reason=f"Client {client.server_name} subscribed to {network_key}",
            )
            wanted = {
                rid
                for rid, existing in (
                    ("publish", publish_channel),
                    ("subscribe", subscribe_channel),
                )
                if existing is None
            }
            layout_resources = compile_client(
                layout_ctx,
                include_subscribed=True,
                channel_ids=wanted,
            )
            layout_resources = [
                replace(resource, name=publish_name)
                if resource.id == "publish"
                else replace(resource, name=subscribe_name)
                if resource.id == "subscribe"
                else resource
                for resource in layout_resources
            ]
            batch = await apply_layout(
                layout_ctx,
                layout_resources,
                mode=ApplyMode.ENSURE,
            )
            if publish_channel is None:
                created = batch.resource("publish")
                if not isinstance(created, discord.TextChannel):
                    detail = batch.failures[0] if batch.failures else "publish create failed"
                    raise RuntimeError(detail)
                publish_channel = created
                newly_created.append(publish_channel)
            if subscribe_channel is None:
                created = batch.resource("subscribe")
                if not isinstance(created, discord.TextChannel):
                    detail = batch.failures[0] if batch.failures else "subscribe create failed"
                    raise RuntimeError(detail)
                subscribe_channel = created
                newly_created.append(subscribe_channel)
        except (discord.HTTPException, RuntimeError) as exc:
            for channel in newly_created:
                try:
                    await channel.delete(
                        reason="Subscription provisioning failed",
                    )
                except discord.HTTPException:
                    pass
            return SubscribeResult(success=False, error=f"Discord API error: {exc}")
    else:
        await sync_subscription_channel_permissions(
            guild,
            bot_member,
            client=client,
            subscription=ClientSubscription(
                id=0,
                client_id=client.id,
                network_id=network_id,
                network_key=network_key,
                publish_channel_id=publish_channel.id,
                subscribe_channel_id=subscribe_channel.id,
                moderation_message_id=None,
                publish_setup_message_id=None,
                subscribe_setup_message_id=None,
        activation_welcome_message_id=None,
        network_welcome_message_id=None,
        network_welcome_complete=False,
        subscribe_confirmed=False,
        enabled=True,
    ),
            access_role_name=access_role_name,
        )

    assert publish_channel is not None
    assert subscribe_channel is not None

    subscription = await client_repo.create_subscription(
        client_id=client.id,
        network_id=network_id,
        network_key=network_key,
        publish_channel_id=publish_channel.id,
        subscribe_channel_id=subscribe_channel.id,
    )
    reactivated = False
    if channels_preexisted and not newly_created:
        subscription = await client_repo.mark_silent_reconnect(subscription.id)
        reactivated = True
    await reorder_client_category_channels(
        category,
        client=client,
        client_repo=client_repo,
        network_repo=network_repo,
    )
    return SubscribeResult(
        success=True,
        subscription=subscription,
        created=True,
        reactivated=reactivated,
    )

async def unsubscribe_client(guild: discord.Guild,
    bot_member: discord.Member,
    *,
    client: Client,
    subscription: ClientSubscription,
    network_key: str,
    client_repo: ClientStore,
    network_repo: NetworkStore,
) -> UnsubscribeResult:
    profile = await resolve_client_profile_channel(guild, client)
    if profile is not None and subscription.moderation_message_id is not None:
        try:
            message = await profile.fetch_message(subscription.moderation_message_id)
            await message.delete()
        except discord.HTTPException:
            pass

    publish = await fetch_publish_channel(guild, subscription)
    if isinstance(publish, discord.TextChannel):
        try:
            for webhook in await publish.webhooks():
                try:
                    await webhook.delete(reason=f"Left network {network_key}")
                except discord.HTTPException:
                    pass
        except discord.HTTPException:
            pass
        try:
            await publish.delete(reason=f"Left network {network_key}")
        except discord.HTTPException:
            logger.warning(
                "Could not delete publish channel while leaving network",
                extra={"channel_id": publish.id},
            )

    subscribe = await fetch_subscribe_channel(guild, subscription)
    if subscribe is not None:
        try:
            await subscribe.delete(reason=f"Left network {network_key}")
        except discord.HTTPException:
            logger.warning(
                "Could not delete subscribe channel while leaving network",
                extra={"channel_id": subscribe.id},
            )

    deleted = await client_repo.delete_subscription_with_relations(subscription.id)
    if deleted is None:
        return UnsubscribeResult(success=False, error="Subscription was not found.")

    category = await resolve_client_category(guild, client)
    if category is not None:
        await reorder_client_category_channels(
            category,
            client=client,
            client_repo=client_repo,
            network_repo=network_repo,
        )

    return UnsubscribeResult(success=True)

class ClientSubscriptionService:
    subscribe_client = staticmethod(subscribe_client)
    unsubscribe_client = staticmethod(unsubscribe_client)

def _category_channels(category: discord.CategoryChannel) -> list[discord.abc.GuildChannel]:
    return [
        ch
        for ch in category.channels
        if not isinstance(ch, discord.CategoryChannel) and hasattr(ch, "name")
    ]


async def sync_client_channel_names(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    client: Client,
    client_repo: ClientStore,
    network_repo: NetworkStore,
) -> None:
    profile = await resolve_client_profile_channel(guild, client)
    if profile is not None:
        target = build_client_profile_channel_base(client.server_name)
        if profile.name.casefold() != target.casefold():
            try:
                await profile.edit(name=target, reason="The Network client channel rename")
            except discord.HTTPException:
                logger.warning(
                    "Could not rename client profile channel",
                    extra={"channel_id": profile.id},
                )

    for subscription in await client_repo.list_subscriptions_by_client(client.id):
        key = subscription.network_key
        if not key and subscription.network_id is not None:
            network = await network_repo.get_by_id(subscription.network_id)
            if network is not None:
                key = network.key
        if not key:
            continue
        publish = await fetch_publish_channel(guild, subscription)
        subscribe = await fetch_subscribe_channel(guild, subscription)
        publish_target = build_client_publish_channel_base(client.server_name, key)
        subscribe_target = build_client_subscribe_channel_base(
            client.server_name,
            key,
        )
        if publish is not None and publish.name.casefold() != publish_target.casefold():
            try:
                await publish.edit(name=publish_target, reason="The Network client channel rename")
            except discord.HTTPException:
                logger.warning(
                    "Could not rename publish channel",
                    extra={"channel_id": publish.id},
                )
        if subscribe is not None and subscribe.name.casefold() != subscribe_target.casefold():
            try:
                await subscribe.edit(  # type: ignore[attr-defined]
                    name=subscribe_target,
                    reason="The Network client channel rename",
                )
            except discord.HTTPException:
                logger.warning(
                    "Could not rename subscribe channel",
                    extra={"channel_id": subscribe.id},
                )


def build_client_category_channel_order(
    client: Client,
    network_keys: Iterable[str],
) -> list[str]:
    order = [build_client_profile_channel_base(client.server_name)]
    for key in sorted(network_keys):
        order.append(build_client_subscribe_channel_base(client.server_name, key))
        order.append(build_client_publish_channel_base(client.server_name, key))
    return order


async def reorder_client_category_channels(
    category: discord.CategoryChannel,
    *,
    client: Client,
    client_repo: ClientStore,
    network_repo: NetworkStore,
) -> None:
    from bot.core.channels.order import align_positions

    subscriptions = await client_repo.list_subscriptions_by_client(client.id)
    order: list[int] = [client.profile_channel_id]

    subs_by_network_key: dict[str, ClientSubscription] = {}
    for sub in subscriptions:
        key = sub.network_key
        if not key and sub.network_id is not None:
            network = await network_repo.get_by_id(sub.network_id)
            if network is not None:
                key = network.key
        if key:
            subs_by_network_key[key] = sub

    for key in sorted(subs_by_network_key):
        sub = subs_by_network_key[key]
        order.append(sub.subscribe_channel_id)
        order.append(sub.publish_channel_id)

    channels_by_id = {ch.id: ch for ch in _category_channels(category)}
    ordered = [
        channels_by_id[channel_id]
        for channel_id in order
        if channel_id in channels_by_id
    ]
    await align_positions(
        ordered,
        reason="The Network client channel order",
    )


async def resync_subscriptions_for_network(
    guild: discord.Guild,
    bot: Any,
    context: Any,
    network: Network,
    *,
    access_role_name: str,
    view_registry: ViewRegistry,
) -> int:
    from bot.features.channels.stickies.subscription import sync_subscription_setup

    bot_member = guild.me
    if bot_member is None:
        return 0

    async def _sync_existing(
        client: Client,
        subscription: ClientSubscription,
        *,
        adopt_zombie: bool = False,
    ) -> ClientSubscription:
        if adopt_zombie and (
            not subscription.subscribe_confirmed or not subscription.network_welcome_complete
        ):
            subscription = await context.store.clients.mark_silent_reconnect(
                subscription.id
            )
        await sync_subscription_channel_permissions(
            guild,
            bot_member,
            client=client,
            subscription=subscription,
            access_role_name=access_role_name,
        )
        category = await resolve_client_category(guild, client)
        if category is not None:
            await reorder_client_category_channels(
                category,
                client=client,
                client_repo=context.store.clients,
                network_repo=context.store.networks,
            )
        # Relinks and rediscoveries must not recreate setup cards or welcomes.
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
        return subscription

    relinked = 0
    for client in await context.store.clients.list_all():
        if client.guild_id != guild.id:
            continue
        category = await resolve_client_category(guild, client)
        if category is None:
            continue

        existing = await context.store.clients.get_subscription(client.id, network.id)
        if existing is not None:
            await _sync_existing(client, existing, adopt_zombie=True)
            continue

        orphan = await context.store.clients.get_subscription_by_client_and_key(
            client.id,
            network.key,
        )
        if orphan is not None and orphan.network_id is None:
            subscription = await context.store.clients.relink_subscription(
                orphan.id,
                network.id,
            )
            await _sync_existing(client, subscription, adopt_zombie=True)
            relinked += 1
            continue

        publish_channel, subscribe_channel = find_network_subscription_channels(
            category,
            network.key,
            client=client,
        )
        if publish_channel is None or subscribe_channel is None:
            continue

        subscription = await context.store.clients.create_subscription(
            client_id=client.id,
            network_id=network.id,
            network_key=network.key,
            publish_channel_id=publish_channel.id,
            subscribe_channel_id=subscribe_channel.id,
        )
        # Channels survived hub uninit: reconnect without setup/welcome spam.
        subscription = await context.store.clients.mark_silent_reconnect(subscription.id)
        await _sync_existing(client, subscription)
        relinked += 1

    if relinked:
        await context.refresh_projections()

    return relinked

