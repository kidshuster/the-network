from __future__ import annotations

import logging
from typing import Any, Literal, cast

import discord

from bot.core.clients.resources import fetch_publish_channel, fetch_subscribe_channel
from bot.core.clients.setup_state import SubscriptionSetupState, resolve_setup_state
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.network import Network
from bot.core.templates import render_embed, render_text
from bot.core.views import ViewRegistry
from bot.features.channels.resolve import (
    HUB_CATEGORY_MODERATION,
    HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
    resolve_hub_category,
    resolve_hub_channel,
)
from bot.features.channels.stickies.loader import sticky_spec
from bot.features.channels.stickies.reconciler import (
    SETUP_STICKY_HISTORY_LIMIT,
    find_embed_sticky_by_footer_scan,
    resolve_embed_sticky_message,
    sync_footer_marker_embed_sticky,
)

logger = logging.getLogger(__name__)

SetupMode = Literal["create", "reconcile"]

_PUBLISH_SPEC = sticky_spec("subscription-publish")
_SUBSCRIBE_SPEC = sticky_spec("subscription-subscribe")
_PUBLISH_SETUP_FOOTER = _PUBLISH_SPEC.footer_marker
_SUBSCRIBE_SETUP_FOOTER = _SUBSCRIBE_SPEC.footer_marker
_SETUP_HISTORY_LIMIT = SETUP_STICKY_HISTORY_LIMIT


def _bot_author_icon_url(bot: Any) -> str:
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


async def _resolve_network_welcome_source(
    bot: Any,
    context: Any,
    guild: discord.Guild,
    subscription: ClientSubscription,
) -> discord.Message | None:
    message_id = subscription.network_welcome_message_id
    if message_id is None or message_id <= 0:
        return None
    mod_category = resolve_hub_category(guild, HUB_CATEGORY_MODERATION)
    channel = resolve_hub_channel(
        guild,
        HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
        category_id=None if mod_category is None else mod_category.id,
        include_announcement=False,
    )
    if channel is None or not hasattr(channel, "fetch_message"):
        return None
    try:
        return await channel.fetch_message(message_id)
    except discord.HTTPException:
        return None


async def _dispatch_network_welcome(
    bot: Any,
    context: Any,
    guild: discord.Guild,
    *,
    client: Client,
    subscription: ClientSubscription,
    message: discord.Message,
) -> bool:
    from bot.features.recipes.hub.announcements import dispatch_system_announcement

    result = await dispatch_system_announcement(
        context,
        guild,
        message,
        about_client_id=client.id,
        exclude_client_id=client.id,
        author_icon_url=_bot_author_icon_url(bot),
    )
    if not result.success:
        logger.warning(
            "Server-wide welcome dispatch was incomplete",
            extra={
                "network_key": subscription.network_key,
                "subscription_id": subscription.id,
                "errors": result.errors,
            },
        )
        return False
    return True


async def _post_network_member_welcome(
    bot: Any,
    context: Any,
    guild: discord.Guild,
    *,
    client: Client,
    network: Network,
    subscription: ClientSubscription,
) -> ClientSubscription:
    """Post/dispatch the network-wide welcome using independent durable state.

    Local subscribe-channel activation messaging uses ``activation_welcome_message_id``.
    Network announcements use ``network_welcome_*`` so either half can retry alone.
    """
    fresh = await context.store.clients.get_subscription_by_id(subscription.id)
    if fresh is None:
        return subscription
    subscription = cast(ClientSubscription, fresh)
    if subscription.network_welcome_complete:
        return subscription

    existing_source = await _resolve_network_welcome_source(
        bot, context, guild, subscription
    )
    if existing_source is not None:
        if await _dispatch_network_welcome(
            bot,
            context,
            guild,
            client=client,
            subscription=subscription,
            message=existing_source,
        ):
            return cast(
                ClientSubscription,
                await context.store.clients.mark_network_welcome_complete(subscription.id),
            )
        return subscription

    if subscription.network_welcome_message_id == 0:
        # Another worker claimed the post; leave retry to a later activation check.
        return subscription

    claimed = await context.store.clients.claim_network_welcome(subscription.id)
    if claimed is None:
        refreshed = await context.store.clients.get_subscription_by_id(subscription.id)
        return cast(ClientSubscription, refreshed or subscription)

    mod_category = resolve_hub_category(guild, HUB_CATEGORY_MODERATION)
    channel = resolve_hub_channel(
        guild,
        HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
        category_id=None if mod_category is None else mod_category.id,
        include_announcement=False,
    )
    if channel is None:
        await context.store.clients.clear_network_welcome_claim(subscription.id)
        return cast(
            ClientSubscription,
            await context.store.clients.get_subscription_by_id(subscription.id)
            or subscription,
        )

    content = render_text(
        "network_member_connected",
        network_display_name=network.display_name,
        network_key=network.key,
        client_server_name=client.server_name,
    ).strip()
    try:
        message = await channel.send(content=content, silent=True)
    except discord.HTTPException:
        logger.warning(
            "Could not post network member welcome",
            extra={"network_key": network.key, "client_id": client.id},
        )
        await context.store.clients.clear_network_welcome_claim(subscription.id)
        return cast(
            ClientSubscription,
            await context.store.clients.get_subscription_by_id(subscription.id)
            or subscription,
        )

    subscription = cast(
        ClientSubscription,
        await context.store.clients.update_network_welcome_message_id(
            subscription.id,
            message.id,
        ),
    )
    if await _dispatch_network_welcome(
        bot,
        context,
        guild,
        client=client,
        subscription=subscription,
        message=message,
    ):
        subscription = cast(
            ClientSubscription,
            await context.store.clients.mark_network_welcome_complete(subscription.id),
        )
    return subscription


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
    context: Any,
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
            _PUBLISH_SPEC.template,
            publish_mention=publish_channel.mention,
        ),
        allow_create=allow_create,
        remove=configured,
    )
    if result.removed:
        if subscription.publish_setup_message_id is not None:
            return cast(
                ClientSubscription,
                await context.store.clients.update_publish_setup_message_id(
                    subscription.id,
                    None,
                ),
            )
        return subscription
    if result.message is None:
        return subscription
    if subscription.publish_setup_message_id != result.message.id:
        return cast(
            ClientSubscription,
            await context.store.clients.update_publish_setup_message_id(
                subscription.id,
                result.message.id,
            ),
        )
    return subscription


async def _sync_subscribe_setup_sticky(
    guild: discord.Guild,
    subscription: ClientSubscription,
    *,
    subscribe_channel: discord.abc.GuildChannel,
    context: Any,
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
            return cast(
                ClientSubscription,
                await context.store.clients.update_subscribe_setup_message_id(
                    subscription.id,
                    None,
                ),
            )
        return subscription

    if not _supports_setup_sticky(subscribe_channel):
        return subscription

    embed = render_embed(
        _SUBSCRIBE_SPEC.template,
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
        return cast(
            ClientSubscription,
            await context.store.clients.update_subscribe_setup_message_id(
                subscription.id,
                result.message.id,
            ),
        )
    return subscription


async def _maybe_post_activation_welcome(
    bot: Any,
    subscription: ClientSubscription,
    *,
    subscribe_channel: discord.abc.GuildChannel,
    context: Any,
    guild: discord.Guild,
    network: Network,
    client: Client,
    setup_state: SubscriptionSetupState,
) -> ClientSubscription:
    """Run local + network welcome transitions when a subscription becomes fully active.

    Full activation is: network enabled AND publish configured AND subscribe confirmed.
    Local subscribe-channel messaging and hub network welcome have independent markers.
    """
    if not setup_state.fully_configured:
        return subscription
    if not hasattr(subscribe_channel, "send"):
        return subscription

    fresh = await context.store.clients.get_subscription_by_id(subscription.id)
    if fresh is None:
        return subscription
    subscription = cast(ClientSubscription, fresh)

    if subscription.activation_welcome_message_id is None:
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
        else:
            await _publish_announcement(message)
            subscription = cast(
                ClientSubscription,
                await context.store.clients.update_activation_welcome_message_id(
                    subscription.id,
                    message.id,
                ),
            )

    return await _post_network_member_welcome(
        bot,
        context,
        guild,
        client=client,
        network=network,
        subscription=subscription,
    )

async def sync_subscription_setup(
    bot: Any,
    context: Any,
    guild: discord.Guild,
    *,
    client: Client,
    subscription: ClientSubscription,
    network: Network | None,
    setup_mode: SetupMode = "create",
    view_registry: ViewRegistry,
) -> SubscriptionSetupState:
    """Refresh setup stickies, moderation card, and profile for one subscription."""
    from bot.features.recipes.hub.clients.profile_sync import (
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
                allow_create=allow_create or subscription.publish_setup_message_id is None,
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
                allow_create=allow_create or subscription.subscribe_setup_message_id is None,
                view_registry=view_registry,
            )
            state = await resolve_setup_state(
                guild,
                subscription,
                network_active=network_active,
            )
            # Welcomes are first-activation only. Relink/reconcile after network
            # recreate must not repost local or network-wide welcome messages.
            if setup_mode == "create":
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
    bot: Any,
    context: Any,
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
    bot: Any,
    context: Any,
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
