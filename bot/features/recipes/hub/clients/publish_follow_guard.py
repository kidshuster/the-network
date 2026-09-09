"""Remediate hub-sourced Channel Follows into client publish channels."""

from __future__ import annotations

import logging
from typing import Protocol

import discord

from bot.core.clients.resources import (
    fetch_publish_channel,
    resolve_client_profile_channel,
)
from bot.core.clients.setup_state import (
    PublishFollowerInspection,
    classify_publish_follower_webhooks,
    inspect_publish_follower_webhooks,
)
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.templates import render_embed

logger = logging.getLogger(__name__)

_DELETE_REASON = "Rejected hub-sourced Channel Follow into publish (feedback loop risk)"


class _ClientsStore(Protocol):
    async def list_all(self) -> list[Client]: ...

    async def list_subscriptions_by_client(
        self, client_id: int
    ) -> list[ClientSubscription]: ...


async def collect_known_hub_channel_ids(
    clients_store: _ClientsStore,
    guild: discord.Guild,
) -> frozenset[int]:
    """Subscribe / announcements channel IDs on this hub (for missing-source fallback)."""
    ids: set[int] = set()
    try:
        clients = await clients_store.list_all()
    except Exception:
        return frozenset()
    for client in clients:
        if client.guild_id != guild.id:
            continue
        for subscription in await clients_store.list_subscriptions_by_client(client.id):
            if subscription.subscribe_channel_id:
                ids.add(int(subscription.subscribe_channel_id))
            if subscription.announcements_channel_id:
                ids.add(int(subscription.announcements_channel_id))
    return frozenset(ids)


async def remediate_hub_sourced_publish_follows(
    guild: discord.Guild,
    *,
    client: Client,
    subscription: ClientSubscription,
    clients_store: _ClientsStore | None = None,
    known_hub_channel_ids: frozenset[int] | None = None,
) -> PublishFollowerInspection | None:
    """Delete hub-sourced follower webhooks; alert profile when any were removed."""
    if client.read_only or not subscription.publish_channel_id:
        return None

    publish = await fetch_publish_channel(guild, subscription)
    if not isinstance(publish, discord.TextChannel):
        return None

    hub_channels = known_hub_channel_ids
    if hub_channels is None and clients_store is not None:
        hub_channels = await collect_known_hub_channel_ids(clients_store, guild)
    if hub_channels is None:
        hub_channels = frozenset()

    inspection = await inspect_publish_follower_webhooks(
        publish,
        hub_guild_id=guild.id,
        known_hub_channel_ids=hub_channels,
    )
    removed = 0
    for webhook in inspection.forbidden:
        try:
            await webhook.delete(reason=_DELETE_REASON)
            removed += 1
        except discord.HTTPException as exc:
            logger.warning(
                "Could not delete forbidden publish follower webhook",
                extra={
                    "webhook_id": getattr(webhook, "id", None),
                    "publish_channel_id": publish.id,
                    "error": str(exc),
                },
            )

    if removed:
        await _notify_profile_publish_follow_rejected(
            guild,
            client=client,
            publish=publish,
        )
        inspection = await inspect_publish_follower_webhooks(
            publish,
            hub_guild_id=guild.id,
            known_hub_channel_ids=hub_channels,
        )

    return inspection


async def _notify_profile_publish_follow_rejected(
    guild: discord.Guild,
    *,
    client: Client,
    publish: discord.TextChannel,
) -> None:
    profile = await resolve_client_profile_channel(guild, client)
    if profile is None:
        return
    try:
        embed = render_embed(
            "publish_follow_rejected",
            publish_mention=publish.mention,
        )
        await profile.send(embed=embed)
    except discord.HTTPException as exc:
        logger.warning(
            "Could not post publish-follow rejection to profile",
            extra={"client_id": client.id, "error": str(exc)},
        )


async def publish_webhook_is_hub_sourced(
    publish_channel: discord.TextChannel,
    *,
    webhook_id: int,
    hub_guild_id: int,
    known_hub_channel_ids: frozenset[int] | set[int] | None = None,
) -> bool:
    """True when the given follower webhook on publish is hub-sourced (or known hub channel)."""
    try:
        webhooks = await publish_channel.webhooks()
    except discord.HTTPException:
        return False
    target = next((webhook for webhook in webhooks if webhook.id == webhook_id), None)
    if target is None or target.type is not discord.WebhookType.channel_follower:
        return False
    inspection = classify_publish_follower_webhooks(
        [target],
        hub_guild_id=hub_guild_id,
        known_hub_channel_ids=known_hub_channel_ids,
    )
    return bool(inspection.forbidden)
