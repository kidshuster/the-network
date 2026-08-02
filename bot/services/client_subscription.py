from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.db.repositories import ClientRepository, NetworkRepository
from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.domain.network import Network
from bot.services.channel_names import (
    build_client_profile_channel_base,
    build_client_publish_channel_base,
    build_client_subscribe_channel_base,
    legacy_publish_channel_name,
    legacy_subscribe_channel_name,
    profile_channel_name_candidates,
    publish_channel_name_candidates,
    subscribe_channel_name_candidates,
)
from bot.services.guild_layout import resolve_human_moderator_role
from bot.services.guild_permissions import (
    build_client_profile_channel_overwrites,
    build_client_publish_channel_overwrites,
    build_client_subscribe_channel_overwrites,
    create_text_channel_with_overwrites,
    filter_configurable_overwrites,
)
from bot.services.network_provision import (
    resolve_access_role,
)

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubscribeResult:
    success: bool
    subscription: ClientSubscription | None = None
    created: bool = False
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
    client: Client | None = None,
) -> tuple[discord.TextChannel | None, discord.abc.GuildChannel | None]:
    if client is not None:
        publish_names = publish_channel_name_candidates(client.server_name, network_key)
        subscribe_names = subscribe_channel_name_candidates(client.server_name, network_key)
    else:
        publish_names = (legacy_publish_channel_name(network_key),)
        subscribe_names = (legacy_subscribe_channel_name(network_key),)

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


async def sync_subscription_channel_permissions(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    client: Client,
    subscription: ClientSubscription,
    access_role_name: str,
) -> None:
    access_role = resolve_access_role(guild, role_name=access_role_name)
    human_moderator_role = resolve_human_moderator_role(guild)
    client_role = guild.get_role(client.client_role_id)
    if client_role is None:
        return

    publish = guild.get_channel(subscription.publish_channel_id)
    subscribe = guild.get_channel(subscription.subscribe_channel_id)
    publish_overwrites = filter_configurable_overwrites(
        bot_member,
        build_client_publish_channel_overwrites(
            guild,
            bot_member,
            client_role,
            access_role,
            human_moderator_role,
        ),
        for_channel=True,
    )
    subscribe_overwrites = filter_configurable_overwrites(
        bot_member,
        build_client_subscribe_channel_overwrites(
            guild,
            bot_member,
            client_role,
            access_role,
            human_moderator_role,
        ),
        for_channel=True,
    )
    reason = "The Network subscription channel sync"
    if isinstance(publish, discord.TextChannel):
        try:
            await publish.edit(overwrites=publish_overwrites, reason=reason)
        except discord.HTTPException:
            logger.warning(
                "Could not sync publish channel permissions",
                extra={"channel_id": publish.id},
            )
    if subscribe is not None:
        try:
            await subscribe.edit(overwrites=subscribe_overwrites, reason=reason)
        except discord.HTTPException:
            logger.warning(
                "Could not sync subscribe channel permissions",
                extra={"channel_id": subscribe.id},
            )


async def sync_client_profile_channel_permissions(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    client: Client,
    access_role_name: str,
) -> None:
    access_role = resolve_access_role(guild, role_name=access_role_name)
    human_moderator_role = resolve_human_moderator_role(guild)
    client_role = guild.get_role(client.client_role_id)
    if client_role is None:
        return
    profile = guild.get_channel(client.profile_channel_id)
    if not isinstance(profile, discord.TextChannel):
        return
    overwrites = filter_configurable_overwrites(
        bot_member,
        build_client_profile_channel_overwrites(
            guild,
            bot_member,
            client_role,
            access_role,
            human_moderator_role,
        ),
        for_channel=True,
    )
    try:
        await profile.edit(overwrites=overwrites, reason="The Network client profile sync")
    except discord.HTTPException:
        logger.warning(
            "Could not sync profile channel permissions",
            extra={"channel_id": profile.id},
        )


class ClientSubscriptionService:
    async def subscribe_client(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        client: Client,
        network_id: int,
        network_key: str,
        client_repo: ClientRepository,
        network_repo: NetworkRepository,
        access_role_name: str,
    ) -> SubscribeResult:
        existing = await client_repo.get_subscription(client.id, network_id)
        if existing is not None:
            return SubscribeResult(success=True, subscription=existing, created=False)

        access_role = resolve_access_role(guild, role_name=access_role_name)
        human_moderator_role = resolve_human_moderator_role(guild)
        client_role = guild.get_role(client.client_role_id)
        if client_role is None:
            return SubscribeResult(success=False, error="Client role was not found.")

        category = guild.get_channel(client.category_id)
        if not isinstance(category, discord.CategoryChannel):
            return SubscribeResult(success=False, error="Client category was not found.")

        publish_name = build_client_publish_channel_base(client.server_name, network_key)
        subscribe_name = build_client_subscribe_channel_base(client.server_name, network_key)

        publish_overwrites = filter_configurable_overwrites(
            bot_member,
            build_client_publish_channel_overwrites(
                guild,
                bot_member,
                client_role,
                access_role,
                human_moderator_role,
            ),
            for_channel=True,
        )
        subscribe_overwrites = filter_configurable_overwrites(
            bot_member,
            build_client_subscribe_channel_overwrites(
                guild,
                bot_member,
                client_role,
                access_role,
                human_moderator_role,
            ),
            for_channel=True,
        )

        publish_channel, subscribe_channel = find_network_subscription_channels(
            category,
            network_key,
            client=client,
        )
        newly_created: list[discord.abc.GuildChannel] = []

        if publish_channel is None or subscribe_channel is None:
            try:
                if publish_channel is None:
                    publish_channel = await create_text_channel_with_overwrites(
                        guild,
                        bot_member,
                        name=publish_name,
                        category=category,
                        overwrites=publish_overwrites,
                        topic=f"Publish channel for network {network_key}",
                        reason=f"Client {client.server_name} subscribed to {network_key}",
                    )
                    newly_created.append(publish_channel)
                if subscribe_channel is None:
                    subscribe_channel = await create_text_channel_with_overwrites(
                        guild,
                        bot_member,
                        name=subscribe_name,
                        category=category,
                        overwrites=subscribe_overwrites,
                        news=True,
                        reason=f"Subscribe channel for network {network_key}",
                    )
                    newly_created.append(subscribe_channel)
            except discord.HTTPException as exc:
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
        )

    async def unsubscribe_client(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        client: Client,
        subscription: ClientSubscription,
        network_key: str,
        client_repo: ClientRepository,
        network_repo: NetworkRepository,
    ) -> UnsubscribeResult:
        profile = guild.get_channel(client.profile_channel_id)
        if isinstance(profile, discord.TextChannel) and subscription.moderation_message_id is not None:
            try:
                message = await profile.fetch_message(subscription.moderation_message_id)
                await message.delete()
            except discord.HTTPException:
                pass

        publish = guild.get_channel(subscription.publish_channel_id)
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

        subscribe = guild.get_channel(subscription.subscribe_channel_id)
        if subscribe is not None:
            try:
                await subscribe.delete(reason=f"Left network {network_key}")
            except discord.HTTPException:
                logger.warning(
                    "Could not delete subscribe channel while leaving network",
                    extra={"channel_id": subscribe.id},
                )

        await client_repo.delete_blacklists_for_subscription(subscription.id)
        deleted = await client_repo.delete_subscription(subscription.id)
        if deleted is None:
            return UnsubscribeResult(success=False, error="Subscription was not found.")

        category = guild.get_channel(client.category_id)
        if isinstance(category, discord.CategoryChannel):
            await reorder_client_category_channels(
                category,
                client=client,
                client_repo=client_repo,
                network_repo=network_repo,
            )

        return UnsubscribeResult(success=True)


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
    client_repo: ClientRepository,
    network_repo: NetworkRepository,
) -> None:
    profile = guild.get_channel(client.profile_channel_id)
    if isinstance(profile, discord.TextChannel):
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
        publish = guild.get_channel(subscription.publish_channel_id)
        subscribe = guild.get_channel(subscription.subscribe_channel_id)
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
                await subscribe.edit(
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
    order = list(profile_channel_name_candidates(client.server_name))
    for key in sorted(network_keys):
        order.extend(subscribe_channel_name_candidates(client.server_name, key))
        order.extend(publish_channel_name_candidates(client.server_name, key))
    return order


async def reorder_client_category_channels(
    category: discord.CategoryChannel,
    *,
    client: Client,
    client_repo: ClientRepository,
    network_repo: NetworkRepository,
) -> None:
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

    for index, channel_id in enumerate(order):
        channel = channels_by_id.get(channel_id)
        if channel is None:
            continue
        try:
            await channel.edit(
                position=index,
                reason="The Network client channel order",
            )
        except discord.HTTPException:
            logger.warning(
                "Could not reorder client category channel",
                extra={"channel_id": channel_id, "category_id": category.id},
            )


async def resync_subscriptions_for_network(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    network: Network,
    *,
    access_role_name: str,
) -> int:
    from bot.services.subscription_setup_sticky import sync_subscription_setup

    bot_member = guild.me
    if bot_member is None:
        return 0

    relinked = 0
    for client in await context.client_repo.list_all():
        if client.guild_id != guild.id:
            continue
        category = guild.get_channel(client.category_id)
        if not isinstance(category, discord.CategoryChannel):
            continue

        existing = await context.client_repo.get_subscription(client.id, network.id)
        if existing is not None:
            await sync_subscription_channel_permissions(
                guild,
                bot_member,
                client=client,
                subscription=existing,
                access_role_name=access_role_name,
            )
            await reorder_client_category_channels(
                category,
                client=client,
                client_repo=context.client_repo,
                network_repo=context.network_repo,
            )
            continue

        orphan = await context.client_repo.get_subscription_by_client_and_key(
            client.id,
            network.key,
        )
        if orphan is not None and orphan.network_id is None:
            subscription = await context.client_repo.relink_subscription(
                orphan.id,
                network.id,
            )
            await sync_subscription_channel_permissions(
                guild,
                bot_member,
                client=client,
                subscription=subscription,
                access_role_name=access_role_name,
            )
            await reorder_client_category_channels(
                category,
                client=client,
                client_repo=context.client_repo,
                network_repo=context.network_repo,
            )
            await sync_subscription_setup(
                bot,
                context,
                guild,
                client=client,
                subscription=subscription,
                network=network,
            )
            relinked += 1
            continue

        publish_channel, subscribe_channel = find_network_subscription_channels(
            category,
            network.key,
            client=client,
        )
        if publish_channel is None or subscribe_channel is None:
            continue

        subscription = await context.client_repo.create_subscription(
            client_id=client.id,
            network_id=network.id,
            network_key=network.key,
            publish_channel_id=publish_channel.id,
            subscribe_channel_id=subscribe_channel.id,
        )
        await sync_subscription_channel_permissions(
            guild,
            bot_member,
            client=client,
            subscription=subscription,
            access_role_name=access_role_name,
        )
        await reorder_client_category_channels(
            category,
            client=client,
            client_repo=context.client_repo,
            network_repo=context.network_repo,
        )
        await sync_subscription_setup(
            bot,
            context,
            guild,
            client=client,
            subscription=subscription,
            network=network,
        )
        relinked += 1

    if relinked:
        await context.client_cache.load_cache()
        await context.routing_service.load_cache()

    return relinked
