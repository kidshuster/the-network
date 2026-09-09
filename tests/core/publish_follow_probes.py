"""Live smoke: reject hub-sourced Channel Follow into publish (feedback-loop guard)."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.app.widgets import PersistentViewRegistry
from bot.core.clients.resources import fetch_publish_channel, resolve_client_profile_channel
from bot.core.clients.setup_state import is_publish_configured
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.network import Network
from bot.features.channels.stickies.subscription import sync_subscription_setup
from bot.features.recipes.hub.clients.publish_follow_guard import (
    collect_known_hub_channel_ids,
    remediate_hub_sourced_publish_follows,
)
from bot.features.recipes.hub.onboarding.service import ServerRequestService
from tests.core.permission_probe import PROBE_PNG
from tests.core.provision_flow import (
    _SmokeProfileAttachment,
    cleanup_smoke_client,
    ensure_smoke_network_key,
)
from tests.core.resource_guard import guild_test_resource_guard

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot
    from bot.app.context import BotContext

logger = logging.getLogger(__name__)

_SMOKE_PREFIX = "Smoke HubFollow "
_PROBE_REASON = "The Network smoke: hub follow reject"
_REJECT_TITLE = "publish follow rejected"
_HISTORY_LIMIT = 40


@dataclass(frozen=True)
class HubFollowRejectSmokeResult:
    server_name: str
    network_key: str


async def cleanup_smoke_hub_follow_clients(
    guild: discord.Guild,
    context: BotContext,
    bot_member: discord.Member,
) -> None:
    for client in await context.store.clients.list_all():
        if client.guild_id != guild.id:
            continue
        if not client.server_name.startswith(_SMOKE_PREFIX):
            continue
        await cleanup_smoke_client(
            guild,
            context,
            server_name=client.server_name,
            bot_member=bot_member,
        )


async def _provision_smoke_client(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    *,
    network: Network,
) -> tuple[Client, ClientSubscription]:
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")

    suffix = secrets.token_hex(3)
    server_name = f"{_SMOKE_PREFIX}{suffix}"
    service = ServerRequestService(context, bot, view_registry=PersistentViewRegistry(bot))
    if not hasattr(bot, "get_guild"):
        bot.get_guild = lambda guild_id: guild if guild.id == guild_id else None  # type: ignore[method-assign]

    stale = await context.store.requests.get_pending_for_requester(bot_member.id)
    if stale is not None:
        await service.deny_request(request_id=stale.id, moderator=bot_member)

    attachment = _SmokeProfileAttachment(PROBE_PNG)
    submit = await service.submit_request(
        guild,
        requester=bot_member,
        server_name=server_name,
        display_name=f"HubFollow {suffix[:6]}",
        profile_image=attachment,
    )
    if not submit.success:
        raise RuntimeError(f"Hub-follow smoke submit failed: {submit.error}")

    pending = await context.store.requests.get_pending_for_requester(bot_member.id)
    if pending is None:
        raise RuntimeError("Hub-follow smoke submit did not create a pending request.")

    approve = await service.approve_request(
        guild,
        request_id=pending.id,
        moderator=bot_member,
    )
    if not approve.success:
        raise RuntimeError(f"Hub-follow smoke accept failed: {approve.error}")

    client = await context.store.clients.get_by_server_name(guild.id, server_name)
    if client is None:
        raise RuntimeError("Hub-follow smoke accept did not register a client.")

    from bot.features.recipes.hub.clients.subscription import ClientSubscriptionService

    sub_service = ClientSubscriptionService()
    subscribe = await sub_service.subscribe_client(
        guild,
        bot_member,
        client=client,
        network_id=network.id,
        network_key=network.key,
        client_repo=context.store.clients,
        network_repo=context.store.networks,
        access_role_name=bot.settings.network_access_role_name,
    )
    if not subscribe.success or subscribe.subscription is None:
        raise RuntimeError(f"Hub-follow smoke subscribe failed: {subscribe.error or 'unknown'}")

    await context.store.requests.delete_by_id(pending.id)
    subscription = subscribe.subscription
    await sync_subscription_setup(
        bot,
        context,
        guild,
        client=client,
        subscription=subscription,
        network=network,
        setup_mode="create",
        view_registry=PersistentViewRegistry(bot),
    )
    return client, subscription


async def _assert_profile_rejection_notice(
    guild: discord.Guild,
    *,
    client: Client,
    bot_user_id: int,
) -> None:
    profile = await resolve_client_profile_channel(guild, client)
    if profile is None or not hasattr(profile, "history"):
        raise RuntimeError("Hub-follow smoke: profile channel missing.")
    marker = _REJECT_TITLE
    try:
        async for message in profile.history(limit=_HISTORY_LIMIT):
            if message.author.id != bot_user_id or not message.embeds:
                continue
            title = (message.embeds[0].title or "").casefold()
            description = (message.embeds[0].description or "").casefold()
            if marker in title or "feedback loop" in description:
                return
    except discord.HTTPException as exc:
        raise RuntimeError(f"Hub-follow smoke: could not scan profile history: {exc}") from exc
    raise RuntimeError(
        "Hub-follow smoke: expected publish-follow rejection notice on the profile channel."
    )


async def run_hub_follow_reject_smoke_flow(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
) -> HubFollowRejectSmokeResult:
    """Follow a hub subscribe (announcement) into publish; expect reject + profile alert."""
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")
    if bot.user is None:
        raise RuntimeError("Bot user is unavailable.")

    network_key = await ensure_smoke_network_key(context, bot, guild)
    network = await context.store.networks.get_by_key(network_key)
    if network is None:
        raise RuntimeError(f"Smoke network {network_key!r} was not found.")

    async with guild_test_resource_guard(guild, bot_member=bot_member):
        await cleanup_smoke_hub_follow_clients(guild, context, bot_member)
        client: Client | None = None
        server_name = ""
        try:
            client, subscription = await _provision_smoke_client(
                guild,
                bot,
                context,
                network=network,
            )
            server_name = client.server_name

            publish = await fetch_publish_channel(guild, subscription)
            if not isinstance(publish, discord.TextChannel):
                raise RuntimeError("Hub-follow smoke: publish channel missing.")

            subscribe = guild.get_channel(subscription.subscribe_channel_id or 0)
            if not isinstance(subscribe, discord.TextChannel) or not subscribe.is_news():
                raise RuntimeError(
                    "Hub-follow smoke: subscribe channel must be an announcement channel."
                )

            # User fuck-up: Follow a hub network announcement feed into publish.
            # ``follow()`` may omit source_guild on the returned webhook payload —
            # re-list publish webhooks and classify with known hub channel ids.
            followed = await subscribe.follow(destination=publish, reason=_PROBE_REASON)
            if followed.type is not discord.WebhookType.channel_follower:
                raise RuntimeError(
                    f"Hub-follow smoke: expected channel_follower webhook, got {followed.type!r}."
                )

            known = await collect_known_hub_channel_ids(context.store.clients, guild)
            known = frozenset({*known, int(subscribe.id)})

            listed = await publish.webhooks()
            follower = next(
                (
                    webhook
                    for webhook in listed
                    if webhook.id == followed.id
                    or (
                        webhook.type is discord.WebhookType.channel_follower
                        and getattr(getattr(webhook, "source_channel", None), "id", None)
                        == subscribe.id
                    )
                ),
                None,
            )
            if follower is None:
                raise RuntimeError(
                    "Hub-follow smoke: channel_follower webhook missing on publish after follow()."
                )

            from bot.core.clients.setup_state import classify_publish_follower_webhooks

            inspection = classify_publish_follower_webhooks(
                [follower],
                hub_guild_id=guild.id,
                known_hub_channel_ids=known,
            )
            if not inspection.forbidden:
                source_guild_id = getattr(getattr(follower, "source_guild", None), "id", None)
                source_channel_id = getattr(
                    getattr(follower, "source_channel", None), "id", None
                )
                raise RuntimeError(
                    "Hub-follow smoke: followed webhook was not classified as hub-sourced "
                    f"(source_guild={source_guild_id!r}, source_channel={source_channel_id!r}, "
                    f"subscribe={subscribe.id})."
                )

            await remediate_hub_sourced_publish_follows(
                guild,
                client=client,
                subscription=subscription,
                clients_store=context.store.clients,
                known_hub_channel_ids=known,
            )

            if await is_publish_configured(
                publish,
                hub_guild_id=guild.id,
                known_hub_channel_ids=known,
            ):
                raise RuntimeError(
                    "Hub-follow smoke: publish still counts as configured after hub follow reject."
                )

            remaining = [
                webhook
                for webhook in await publish.webhooks()
                if webhook.type is discord.WebhookType.channel_follower
            ]
            if remaining:
                raise RuntimeError(
                    "Hub-follow smoke: hub follower webhook(s) still present after remediate: "
                    + ", ".join(str(webhook.id) for webhook in remaining)
                )

            await _assert_profile_rejection_notice(
                guild,
                client=client,
                bot_user_id=bot.user.id,
            )

            # Sticky sync should treat publish as not configured again.
            await sync_subscription_setup(
                bot,
                context,
                guild,
                client=client,
                subscription=subscription,
                network=network,
                setup_mode="reconcile",
                view_registry=PersistentViewRegistry(bot),
            )

            return HubFollowRejectSmokeResult(
                server_name=server_name,
                network_key=network.key,
            )
        finally:
            if server_name:
                await cleanup_smoke_client(
                    guild,
                    context,
                    server_name=server_name,
                    bot_member=bot_member,
                )
