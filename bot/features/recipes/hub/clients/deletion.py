from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.app.recipes.registry import recipe
from bot.app.recipes.runtime import RecipeContext
from bot.core.clients.resources import fetch_client_role, resolve_client_category
from bot.core.models.client import Client

if TYPE_CHECKING:
    from bot.app.context import BotContext
    from bot.core.database.store import ClientStore, NetworkStore

logger = logging.getLogger(__name__)

_DELETE_REASON = "The Network client deletion"


@dataclass(frozen=True)
class DeleteClientResult:
    success: bool
    error: str | None = None


async def delete_client_resources(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    client: Client,
    client_repo: ClientStore,
    network_repo: NetworkStore,
    context: BotContext,
) -> DeleteClientResult:
    from bot.features.recipes.hub.clients.subscription import unsubscribe_client

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
            return DeleteClientResult(
                success=False,
                error=result.error or "Could not remove a network subscription.",
            )

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
                await _realign_categories_after_client_delete(guild)
        else:
            logger.warning(
                "Client deletion: category still has channels after cleanup",
                extra={"category_id": category.id},
            )

    for channel_id in channel_ids:
        await _delete_client_channel_by_id(
            guild,
            channel_id,
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

    deleted = await client_repo.delete_with_relations(client.id)
    if deleted is None:
        return DeleteClientResult(success=False, error="Client was not found.")

    await context.refresh_projections()
    return DeleteClientResult(success=True)


@recipe("client.delete")
async def delete_client(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    client: Client,
) -> DeleteClientResult:
    return await delete_client_resources(
        guild,
        bot_member,
        client=client,
        client_repo=recipe_context.core.store.clients,
        network_repo=recipe_context.core.store.networks,
        context=recipe_context.core,
    )


async def _realign_categories_after_client_delete(guild: discord.Guild) -> None:
    from bot.app.layout.loader import load_layout
    from bot.app.layout.managed import hub_category_name
    from bot.core.channels.order import align_categories_hub_first

    by_name = {category.name: category for category in guild.categories}
    hub_categories: list[discord.CategoryChannel] = []
    for category_id in load_layout().layout.categories:
        match = by_name.get(hub_category_name(category_id))
        if isinstance(match, discord.CategoryChannel):
            hub_categories.append(match)
    if not hub_categories:
        return
    await align_categories_hub_first(
        guild,
        hub_categories,
        reason=f"{_DELETE_REASON}: category order",
    )


async def _delete_client_channel(
    channel: discord.abc.GuildChannel,
    *,
    reason: str = _DELETE_REASON,
) -> None:
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
    await _delete_client_channel(channel_obj, reason=reason)
