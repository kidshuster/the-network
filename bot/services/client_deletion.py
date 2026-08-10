from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.services.client_resources import fetch_client_role, resolve_client_category

if TYPE_CHECKING:
    from bot.context import BotContext
    from bot.db.repositories import ClientRepository, NetworkRepository
    from bot.domain.client import Client

logger = logging.getLogger(__name__)

_DELETE_REASON = "The Network client deletion"


@dataclass(frozen=True)
class DeleteClientResult:
    success: bool
    error: str | None = None


async def _delete_client_channel(
    channel: discord.abc.GuildChannel,
    *,
    bot_member: discord.Member | None,
    reason: str = _DELETE_REASON,
) -> None:
    if (
        bot_member is not None
        and channel.category is not None
        and not channel.permissions_for(bot_member).manage_channels
    ):
        try:
            await channel.edit(sync_permissions=True, reason=reason)  # type: ignore[attr-defined]
        except discord.HTTPException:
            pass

    if isinstance(channel, discord.TextChannel) and not channel.is_news():
        try:
            webhooks = await channel.webhooks()
        except discord.HTTPException:
            webhooks = []
        for webhook in webhooks:
            try:
                await webhook.delete(reason=reason)
            except discord.HTTPException:
                logger.warning(
                    "Client deletion: could not delete webhook",
                    extra={"channel_id": channel.id, "webhook_id": webhook.id},
                )

    try:
        await channel.delete(reason=reason)
    except discord.NotFound:
        return
    except discord.HTTPException as exc:
        logger.warning(
            "Client deletion: could not delete channel",
            extra={"channel_id": channel.id, "status": exc.status, "text": exc.text},
        )


async def _delete_client_channel_by_id(
    guild: discord.Guild,
    channel_id: int,
    *,
    bot_member: discord.Member | None,
    reason: str = _DELETE_REASON,
) -> None:
    channel_obj: discord.abc.GuildChannel | None = guild.get_channel(channel_id)
    if channel_obj is None:
        try:
            fetched = await guild.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden):
            return
        if not isinstance(fetched, discord.abc.GuildChannel):
            return
        channel_obj = fetched
    await _delete_client_channel(channel_obj, bot_member=bot_member, reason=reason)


class ClientDeletionService:
    async def delete_client(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        client: Client,
        client_repo: ClientRepository,
        network_repo: NetworkRepository,
        context: BotContext,
    ) -> DeleteClientResult:
        from bot.services.client_subscription import ClientSubscriptionService

        subscriptions = await client_repo.list_subscriptions_by_client(client.id)
        sub_service = ClientSubscriptionService()
        for subscription in subscriptions:
            network_key = subscription.network_key or "network"
            result = await sub_service.unsubscribe_client(
                guild,
                bot_member,
                client=client,
                subscription=subscription,
                network_key=network_key,
                client_repo=client_repo,
                network_repo=network_repo,
            )
            if not result.success:
                return DeleteClientResult(
                    success=False,
                    error=result.error or "Could not remove a network subscription.",
                )

        await client_repo.delete_blacklists_blocking_client(client.id)

        if client.emoji_id is not None:
            emoji = guild.get_emoji(client.emoji_id)
            if emoji is not None:
                try:
                    await emoji.delete(reason=_DELETE_REASON)
                except discord.HTTPException:
                    logger.warning(
                        "Client deletion: could not delete client emoji",
                        extra={"client_id": client.id},
                    )

        client_role = await fetch_client_role(guild, client)

        if client_role is not None:
            for member in guild.members:
                if client_role in member.roles:
                    try:
                        await member.remove_roles(client_role, reason=_DELETE_REASON)
                    except discord.HTTPException:
                        logger.warning(
                            "Client deletion: could not remove client role from member",
                            extra={"member_id": member.id, "role_id": client_role.id},
                        )

        channel_ids = {client.profile_channel_id}
        category = await resolve_client_category(guild, client)

        if category is not None:
            for channel in list(category.channels):
                channel_ids.add(channel.id)
                await _delete_client_channel(
                    channel,
                    bot_member=bot_member,
                    reason=_DELETE_REASON,
                )
            if not category.channels:
                try:
                    await category.delete(reason=_DELETE_REASON)
                except discord.HTTPException:
                    logger.warning(
                        "Client deletion: could not delete client category",
                        extra={"category_id": category.id},
                    )
            else:
                logger.warning(
                    "Client deletion: category still has channels after cleanup",
                    extra={"category_id": category.id},
                )

        for channel_id in channel_ids:
            await _delete_client_channel_by_id(
                guild,
                channel_id,
                bot_member=bot_member,
                reason=_DELETE_REASON,
            )

        if client_role is not None:
            try:
                await client_role.delete(reason=_DELETE_REASON)
            except discord.HTTPException:
                logger.warning(
                    "Client deletion: could not delete client role",
                    extra={"role_id": client_role.id},
                )

        deleted = await client_repo.delete(client.id)
        if deleted is None:
            return DeleteClientResult(success=False, error="Client was not found.")

        await context.refresh_client_counts()
        await context.routing_service.load_cache()
        return DeleteClientResult(success=True)
