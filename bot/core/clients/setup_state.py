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


async def is_publish_configured(publish_channel: discord.TextChannel) -> bool:
    try:
        webhooks = await publish_channel.webhooks()
    except discord.HTTPException:
        return False
    for webhook in webhooks:
        if webhook.type is discord.WebhookType.channel_follower:
            return True
    return False


async def resolve_setup_state(
    guild: discord.Guild,
    subscription: ClientSubscription,
    *,
    network_active: bool,
    read_only: bool = False,
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
            publish_ok = await is_publish_configured(publish_channel)
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
