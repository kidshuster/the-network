from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.domain.client import Client
from bot.services.client_permission_rectification import rectify_client_permissions
from bot.services.client_profile_sync import refresh_client_profile_message
from bot.services.client_subscription import (
    reorder_client_category_channels,
    resync_subscriptions_for_network,
    sync_client_channel_names,
)
from bot.services.subscription_setup_sticky import sync_subscription_setup
from bot.ui.network_views import NetworkProfileView

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext
    from bot.services.guild_init import GuildInitResult

logger = logging.getLogger(__name__)


async def reconnect_clients_on_init(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    clients: list[Client],
    *,
    result: GuildInitResult,
    access_role_name: str | None = None,
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
        rectified = await rectify_client_permissions(
            guild,
            bot_member,
            context,
            client,
            access_role=access_role,
            human_moderator_role=human_moderator_role,
            access_role_name=role_name,
        )
        result.rectifications.extend(rectified.rectification_notes())
        result.rectification_skipped.extend(rectified.skip_notes())
        result.rectification_failures.extend(rectified.failure_notes())

        if rectified.skipped and not rectified.synced:
            continue

        category = guild.get_channel(client.category_id)
        if not isinstance(category, discord.CategoryChannel):
            continue

        try:
            await sync_client_channel_names(
                guild,
                bot_member,
                client=client,
                client_repo=context.client_repo,
                network_repo=context.network_repo,
            )

            subscriptions = await context.client_repo.list_subscriptions_by_client(
                client.id,
            )
            for subscription in subscriptions:
                network = await context.network_repo.get_by_id(subscription.network_id)
                if network is None:
                    continue
                await sync_subscription_setup(
                    bot,
                    context,
                    guild,
                    client=client,
                    subscription=subscription,
                    network=network,
                    setup_mode="reconcile",
                )

            await reorder_client_category_channels(
                category,
                client=client,
                client_repo=context.client_repo,
                network_repo=context.network_repo,
            )

            all_networks = await context.network_repo.list_all()
            bot.add_view(
                NetworkProfileView(
                    bot,
                    client.id,
                    [network.key for network in all_networks],
                    timecode_enabled=client.timecode_enabled,
                ),
            )
            await refresh_client_profile_message(bot, context, guild, client)
            reconnected += 1
        except discord.HTTPException as exc:
            result.rectification_failures.append(
                f"**{client.server_name}**: could not finish reconnect ({exc})"
            )
            logger.warning(
                "Client reconnect failed",
                extra={"client_id": client.id, "error": str(exc)},
            )

    for network in await context.network_repo.list_all():
        relinked = await resync_subscriptions_for_network(
            guild,
            bot,
            context,
            network,
            access_role_name=role_name,
        )
        if relinked:
            result.rectifications.append(
                f"Relinked {relinked} subscription(s) for network `{network.key}`."
            )

    if reconnected:
        result.rectifications.append(
            f"Verified and refreshed {reconnected} client profile card(s)."
        )
