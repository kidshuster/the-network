from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import discord

from bot.core.models.client_subscription import ClientSubscription

NetworkLinkStatus = Literal["Active", "Disabled", "Not Configured"]


@dataclass(frozen=True)
class SubscriptionSetupState:
    publish_configured: bool
    subscribe_confirmed: bool
    network_active: bool
    read_only: bool = False

    @property
    def fully_configured(self) -> bool:
        if not self.network_active:
            return False
        if not self.subscribe_confirmed:
            return False
        if self.read_only:
            return True
        return self.publish_configured

    @property
    def link_status(self) -> NetworkLinkStatus:
        if not self.network_active:
            return "Disabled"
        if self.read_only:
            if not self.subscribe_confirmed:
                return "Not Configured"
            return "Active"
        if not self.publish_configured or not self.subscribe_confirmed:
            return "Not Configured"
        return "Active"


@dataclass(frozen=True)
class PublishFollowerInspection:
    """Classification of Channel Follow webhooks on a hub publish channel."""

    valid: tuple[discord.Webhook, ...]
    forbidden: tuple[discord.Webhook, ...]
    unknown: tuple[discord.Webhook, ...]

    @property
    def configured(self) -> bool:
        return bool(self.valid)


def _follower_webhooks(webhooks: list[discord.Webhook]) -> list[discord.Webhook]:
    return [webhook for webhook in webhooks if webhook.type is discord.WebhookType.channel_follower]


def classify_publish_follower_webhooks(
    webhooks: list[discord.Webhook],
    *,
    hub_guild_id: int,
    known_hub_channel_ids: frozenset[int] | set[int] | None = None,
) -> PublishFollowerInspection:
    """Split follower webhooks into external (valid), hub-sourced (forbidden), unknown.

    Hub-sourced follows (``source_guild.id == hub_guild_id``) create relay feedback
    loops when a network subscribe/announcement channel is Followed into publish.
    """
    hub_channels = frozenset(known_hub_channel_ids or ())
    valid: list[discord.Webhook] = []
    forbidden: list[discord.Webhook] = []
    unknown: list[discord.Webhook] = []

    for webhook in _follower_webhooks(webhooks):
        source_guild = getattr(webhook, "source_guild", None)
        source_channel = getattr(webhook, "source_channel", None)
        source_guild_id = getattr(source_guild, "id", None)
        source_channel_id = getattr(source_channel, "id", None)

        if source_guild_id is not None and int(source_guild_id) == int(hub_guild_id):
            forbidden.append(webhook)
            continue
        if source_guild_id is None:
            if source_channel_id is not None and int(source_channel_id) in hub_channels:
                forbidden.append(webhook)
            else:
                unknown.append(webhook)
            continue
        valid.append(webhook)

    return PublishFollowerInspection(
        valid=tuple(valid),
        forbidden=tuple(forbidden),
        unknown=tuple(unknown),
    )


async def inspect_publish_follower_webhooks(
    publish_channel: discord.TextChannel,
    *,
    hub_guild_id: int | None = None,
    known_hub_channel_ids: frozenset[int] | set[int] | None = None,
) -> PublishFollowerInspection:
    hub_id = int(hub_guild_id if hub_guild_id is not None else publish_channel.guild.id)
    try:
        webhooks = await publish_channel.webhooks()
    except discord.HTTPException:
        return PublishFollowerInspection(valid=(), forbidden=(), unknown=())
    return classify_publish_follower_webhooks(
        list(webhooks),
        hub_guild_id=hub_id,
        known_hub_channel_ids=known_hub_channel_ids,
    )


async def is_publish_configured(
    publish_channel: discord.TextChannel,
    *,
    hub_guild_id: int | None = None,
    known_hub_channel_ids: frozenset[int] | set[int] | None = None,
) -> bool:
    inspection = await inspect_publish_follower_webhooks(
        publish_channel,
        hub_guild_id=hub_guild_id,
        known_hub_channel_ids=known_hub_channel_ids,
    )
    return inspection.configured


async def resolve_setup_state(
    guild: discord.Guild,
    subscription: ClientSubscription,
    *,
    network_active: bool,
    read_only: bool = False,
    known_hub_channel_ids: frozenset[int] | set[int] | None = None,
) -> SubscriptionSetupState:
    if read_only:
        return SubscriptionSetupState(
            publish_configured=True,
            subscribe_confirmed=subscription.subscribe_confirmed,
            network_active=network_active,
            read_only=True,
        )
    publish_ok = False
    if subscription.publish_channel_id:
        publish_channel = guild.get_channel(subscription.publish_channel_id)
        if isinstance(publish_channel, discord.TextChannel):
            publish_ok = await is_publish_configured(
                publish_channel,
                hub_guild_id=guild.id,
                known_hub_channel_ids=known_hub_channel_ids,
            )
    return SubscriptionSetupState(
        publish_configured=publish_ok,
        subscribe_confirmed=subscription.subscribe_confirmed,
        network_active=network_active,
        read_only=False,
    )


def derive_network_link_status(
    *,
    network_active: bool,
    publish_configured: bool,
    subscribe_confirmed: bool,
    read_only: bool = False,
) -> NetworkLinkStatus:
    if not network_active:
        return "Disabled"
    if read_only:
        if not subscribe_confirmed:
            return "Not Configured"
        return "Active"
    if not publish_configured or not subscribe_confirmed:
        return "Not Configured"
    return "Active"
