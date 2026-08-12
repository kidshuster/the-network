from __future__ import annotations

import logging
from typing import Any

import discord

from bot.core.media.emoji import EmojiService, emoji_sync_target_from_client
from bot.core.models.client import Client
from bot.core.models.profile_image import ProfileImage
from bot.core.models.server_request import ServerRequest
from bot.core.views import ViewRegistry
from bot.features.recipes.hub.clients.deletion import purge_client_discord_resources
from bot.features.recipes.hub.clients.profile_post import build_client_profile_embed
from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message
from bot.features.recipes.hub.clients.provision import provision_client
from bot.features.recipes.hub.clients.subscription import unsubscribe_client

logger = logging.getLogger(__name__)


async def reconcile_client_from_request(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    bot: Any,
    context: Any,
    request: ServerRequest,
    client: Client,
    image: ProfileImage,
    view_registry: ViewRegistry,
    access_role_name: str,
    operator_role_name: str,
) -> tuple[Client, discord.Role, discord.TextChannel]:
    """Rebuild Discord resources for an existing malformed client row."""
    client_repo = context.store.clients
    network_repo = context.store.networks

    subscriptions = await client_repo.list_subscriptions_by_client(client.id)
    for subscription in subscriptions:
        network_key = subscription.network_key or "network"
        result = await unsubscribe_client(
            guild,
            bot_member,
            client=client,
            subscription=subscription,
            network_key=network_key,
            client_repo=client_repo,
            network_repo=network_repo,
        )
        if not result.success:
            logger.warning(
                "Repair reconcile: unsubscribe failed; clearing subscription row",
                extra={
                    "client_id": client.id,
                    "subscription_id": subscription.id,
                    "error": result.error,
                },
            )
            await client_repo.delete_subscription_with_relations(subscription.id)

    await client_repo.clear_subscriptions_with_relations(client.id)
    await purge_client_discord_resources(guild, client)

    provision = await provision_client(
        guild,
        bot_member,
        server_name=request.server_name,
        access_role_name=access_role_name,
        operator_role_name=operator_role_name,
    )
    network_keys = [network.key for network in await network_repo.list_all()]
    starter = await provision.profile_channel.send(
        embed=build_client_profile_embed(
            server_name=request.server_name,
            display_name=request.display_name,
            enabled=True,
        ),
        view=view_registry.register_client_profile_view(client.id, network_keys),
        silent=True,
    )
    client = await client_repo.update_provisioned_resources(
        client.id,
        category_id=provision.category.id,
        client_role_id=provision.client_role.id,
        profile_channel_id=provision.profile_channel.id,
        profile_message_id=starter.id,
        display_name=request.display_name,
    )
    await starter.edit(
        view=view_registry.register_client_profile_for_client(client, network_keys)
    )
    emoji = await EmojiService().sync_for_profile(
        guild,
        emoji_sync_target_from_client(client, source_channel_id=provision.profile_channel.id),
        image,
        previous_hash=None,
        previous_emoji_id=None,
        force=True,
    )
    if emoji.emoji_id is not None:
        await client_repo.update_emoji_fields(
            client.id,
            emoji_id=emoji.emoji_id,
            emoji_name=emoji.emoji_name,
            image_hash=emoji.image_hash,
            degraded_reason=emoji.degraded_reason,
        )
        client = await client_repo.get_by_id(client.id) or client
    await refresh_client_profile_message(
        bot, context, guild, client, view_registry=view_registry
    )
    return client, provision.client_role, provision.profile_channel
