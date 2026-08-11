from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from bot.clients.names import slugify_client_name
from bot.clients.resources import (
    fetch_client_role,
    fetch_publish_channel,
    fetch_subscribe_channel,
    resolve_client_category,
    resolve_client_profile_channel,
)
from bot.clients.subscription import resolve_subscription_channels_in_category
from bot.domain.client import Client
from bot.layout import ApplyMode, LayoutContext, apply_layout, compile_client
from bot.networks.roles import resolve_operator_role_by_name

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
    _ = access_role_name
    outcome = ClientRectificationResult(server_name=client.server_name)

    category = await resolve_client_category(guild, client)
    if category is None:
        outcome.skipped.append("category missing in Discord")
        return outcome

    client_role = await fetch_client_role(guild, client)
    if client_role is None:
        outcome.skipped.append("client role missing in Discord")
        return outcome

    try:
        operator_role = resolve_operator_role_by_name(guild, role_name="The Network+")
    except Exception:
        operator_role = None
    if not isinstance(operator_role, discord.Role):
        operator_role = None
    layout_ctx = LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access_role,
        moderator_role=human_moderator_role,
        operator_role=operator_role,
        client_role=client_role,
        server_name=client.server_name,
        slug=slugify_client_name(client.server_name),
        reason="The Network server init",
    )

    try:
        batch = await apply_layout(
            layout_ctx,
            compile_client(layout_ctx),
            mode=ApplyMode.RECONCILE_ONLY,
        )
        for item in batch.results:
            if item.resource_id == "client":
                if item.success:
                    outcome.synced.append("category")
                else:
                    outcome.failures.append(
                        f"could not sync category permissions ({item.detail})",
                    )
            elif item.resource_id == "profile":
                profile = await resolve_client_profile_channel(guild, client)
                if profile is None:
                    outcome.skipped.append("profile channel missing in Discord")
                elif item.success:
                    outcome.synced.append(profile.mention)
                else:
                    outcome.failures.append(
                        f"could not sync {profile.mention} ({item.detail})",
                    )
    except discord.HTTPException as exc:
        outcome.failures.append(f"could not sync category permissions ({exc})")

    profile = await resolve_client_profile_channel(guild, client)
    if profile is None and "profile channel missing in Discord" not in outcome.skipped:
        outcome.skipped.append("profile channel missing in Discord")

    subscriptions = await context.store.clients.list_subscriptions_by_client(client.id)
    for subscription in subscriptions:
        network_id = subscription.network_id
        if network_id is None:
            outcome.skipped.append("subscription network id missing from database")
            continue
        network = await context.store.networks.get_by_id(network_id)
        if network is None:
            outcome.skipped.append(
                f"subscription network id {network_id} missing from database"
            )
            continue

        publish = await fetch_publish_channel(guild, subscription)
        subscribe = await fetch_subscribe_channel(guild, subscription)
        if publish is None or subscribe is None:
            publish, subscribe = resolve_subscription_channels_in_category(
                guild,
                category,
                subscription,
                network.key,
                client=client,
            )

        sub_ctx = LayoutContext(
            guild=guild,
            bot_member=bot_member,
            access_role=access_role,
            moderator_role=human_moderator_role,
            operator_role=operator_role,
            client_role=client_role,
            server_name=client.server_name,
            slug=slugify_client_name(client.server_name),
            network_key=network.key,
            reason="The Network server init",
        )
        try:
            sub_batch = await apply_layout(
                sub_ctx,
                compile_client(
                    sub_ctx,
                    include_subscribed=True,
                    channel_ids={"publish", "subscribe"},
                ),
                mode=ApplyMode.RECONCILE_ONLY,
            )
            if not sub_batch.success:
                outcome.failures.append(
                    f"could not sync `{network.key}` subscription channels "
                    f"({'; '.join(sub_batch.failures)})"
                )
                continue
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
