from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from bot.domain.client import Client
from bot.services.client_subscription import (
    find_network_subscription_channels,
    sync_client_profile_channel_permissions,
    sync_subscription_channel_permissions,
)
from bot.services.guild_permissions import sync_client_category_permissions

if TYPE_CHECKING:
    from bot.context import BotContext


@dataclass
class ClientRectificationResult:
    server_name: str
    synced: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def rectification_notes(self) -> list[str]:
        if self.synced:
            channels = ", ".join(self.synced)
            return [f"**{self.server_name}**: rectified {channels}."]
        return []

    def skip_notes(self) -> list[str]:
        return [f"**{self.server_name}**: {reason}" for reason in self.skipped]

    def failure_notes(self) -> list[str]:
        return [f"**{self.server_name}**: {reason}" for reason in self.failures]


async def rectify_client_permissions(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    client: Client,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    access_role_name: str,
) -> ClientRectificationResult:
    """Validate a stored client profile and sync missing channel permissions."""
    outcome = ClientRectificationResult(server_name=client.server_name)

    category = guild.get_channel(client.category_id)
    if not isinstance(category, discord.CategoryChannel):
        outcome.skipped.append("category missing in Discord")
        return outcome

    client_role = guild.get_role(client.client_role_id)
    if client_role is None:
        outcome.skipped.append("client role missing in Discord")
        return outcome

    try:
        await sync_client_category_permissions(
            category,
            bot_member,
            client_role,
            access_role,
            human_moderator_role,
            reason="The Network server init",
        )
        outcome.synced.append("category")
    except discord.HTTPException as exc:
        outcome.failures.append(f"could not sync category permissions ({exc})")

    profile = guild.get_channel(client.profile_channel_id)
    if isinstance(profile, discord.TextChannel):
        try:
            await sync_client_profile_channel_permissions(
                guild,
                bot_member,
                client=client,
                access_role_name=access_role_name,
            )
            outcome.synced.append(profile.mention)
        except discord.HTTPException as exc:
            outcome.failures.append(f"could not sync {profile.mention} ({exc})")
    else:
        outcome.skipped.append("profile channel missing in Discord")

    subscriptions = await context.client_repo.list_subscriptions_by_client(client.id)
    for subscription in subscriptions:
        network = await context.network_repo.get_by_id(subscription.network_id)
        if network is None:
            outcome.skipped.append(
                f"subscription network id {subscription.network_id} missing from database"
            )
            continue

        publish = guild.get_channel(subscription.publish_channel_id)
        subscribe = guild.get_channel(subscription.subscribe_channel_id)
        if publish is None or subscribe is None:
            found_publish, found_subscribe = find_network_subscription_channels(
                category,
                network.key,
                client=client,
            )
            if publish is None:
                publish = found_publish
            if subscribe is None:
                subscribe = found_subscribe

        try:
            await sync_subscription_channel_permissions(
                guild,
                bot_member,
                client=client,
                subscription=subscription,
                access_role_name=access_role_name,
            )
        except discord.HTTPException as exc:
            outcome.failures.append(
                f"could not sync `{network.key}` subscription channels ({exc})"
            )
            continue

        if isinstance(publish, discord.TextChannel):
            outcome.synced.append(f"{publish.mention} (`{network.key}` publish)")
        if subscribe is not None:
            outcome.synced.append(f"{subscribe.mention} (`{network.key}` subscribe)")

    return outcome
