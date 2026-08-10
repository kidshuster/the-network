from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.services.guild_layout import resolve_network_announcements_channel
from bot.services.hub_announcements import (
    dispatch_hub_announcement,
    ensure_hub_announcements_client,
    inject_hub_announcement,
)
from bot.services.permission_probe import PROBE_PNG
from bot.services.server_request_service import ServerRequestService
from bot.smoke.provision_flow import (
    _SmokeProfileAttachment,
    cleanup_smoke_client,
    ensure_smoke_network_key,
)
from bot.smoke.resource_guard import guild_test_resource_guard
from bot.ui.persistent_views import PersistentViewRegistry

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

_SMOKE_HUB_SUB_PREFIX = "Smoke HubSub "
_HISTORY_LIMIT = 30


@dataclass(frozen=True)
class HubAnnouncementsSmokeResult:
    hub_client_id: int
    subscriber_server_name: str
    network_key: str


async def _provision_smoke_subscriber(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    *,
    network_key: str,
) -> tuple[str, int]:
    network = await context.network_repo.get_by_key(network_key)
    if network is None:
        raise RuntimeError(f"Smoke network {network_key!r} not found")

    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")

    suffix = secrets.token_hex(3)
    server_name = f"{_SMOKE_HUB_SUB_PREFIX}{suffix}"
    service = ServerRequestService(context, bot, view_registry=PersistentViewRegistry(bot))
    if not hasattr(bot, "get_guild"):
        bot.get_guild = lambda guild_id: guild if guild.id == guild_id else None  # type: ignore[method-assign]

    stale = await context.server_request_repo.get_pending_for_requester(bot_member.id)
    if stale is not None:
        await service.deny_request(request_id=stale.id, moderator=bot_member)

    attachment = _SmokeProfileAttachment(PROBE_PNG)
    submit = await service.submit_request(
        guild,
        requester=bot_member,
        server_name=server_name,
        display_name=f"Smoke HubSub {suffix[:6]}",
        profile_image=attachment,
    )
    if not submit.success:
        raise RuntimeError(f"Smoke subscriber submit failed: {submit.error}")

    pending = await context.server_request_repo.get_pending_for_requester(bot_member.id)
    if pending is None:
        raise RuntimeError("Smoke subscriber submit did not create a pending request.")

    approve = await service.approve_request(
        guild,
        request_id=pending.id,
        moderator=bot_member,
    )
    if not approve.success:
        raise RuntimeError(f"Smoke subscriber accept failed: {approve.message}")

    from bot.services.client_subscription import ClientSubscriptionService

    client = await context.client_repo.get_by_server_name(guild.id, server_name)
    if client is None:
        raise RuntimeError("Smoke subscriber client missing after accept")

    sub_service = ClientSubscriptionService()
    subscribe = await sub_service.subscribe_client(
        guild,
        bot_member,
        client=client,
        network_id=network.id,
        network_key=network.key,
        client_repo=context.client_repo,
        network_repo=context.network_repo,
        access_role_name=bot.settings.network_access_role_name,
    )
    if not subscribe.success or subscribe.subscription is None:
        raise RuntimeError(
            f"Smoke subscriber network join failed: {subscribe.error or 'unknown'}"
        )

    await context.server_request_repo.delete_by_id(pending.id)
    return server_name, subscribe.subscription.subscribe_channel_id


async def _recent_bot_text_messages(
    channel: discord.abc.GuildChannel,
    *,
    bot_user_id: int,
    limit: int = _HISTORY_LIMIT,
) -> list[discord.Message]:
    if not hasattr(channel, "history"):
        return []
    matches: list[discord.Message] = []
    try:
        async for message in channel.history(limit=limit):
            if message.author.id == bot_user_id:
                matches.append(message)
    except discord.HTTPException:
        pass
    return matches


async def _ensure_channel_follow(
    source: discord.TextChannel,
    destination: discord.TextChannel,
) -> None:
    try:
        webhooks = await destination.webhooks()
    except discord.HTTPException:
        webhooks = []
    for webhook in webhooks:
        if webhook.type is not discord.WebhookType.channel_follower:
            continue
        source_channel = webhook.source_channel
        if source_channel is not None and source_channel.id == source.id:
            return
    try:
        await source.follow(destination=destination, reason="The Network hub announcements smoke")
    except discord.HTTPException as exc:
        raise RuntimeError(
            f"Could not link Channel Follow from {source.mention} to "
            f"{destination.mention}: {exc}"
        ) from exc


async def _channel_contains_token(
    channel: discord.TextChannel,
    token: str,
    *,
    limit: int = 25,
) -> bool:
    try:
        async for message in channel.history(limit=limit):
            if token in (message.content or ""):
                return True
            for embed in message.embeds:
                if token in (embed.description or ""):
                    return True
    except discord.HTTPException:
        pass
    return False


async def _wait_for_channel_token(
    channel: discord.TextChannel,
    token: str,
    *,
    timeout_seconds: float = 20.0,
) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        if await _channel_contains_token(channel, token):
            return True
        await asyncio.sleep(2.0)
    return False


async def run_hub_announcements_smoke_flow(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
) -> HubAnnouncementsSmokeResult:
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")

    network_key = await ensure_smoke_network_key(context, bot, guild)
    subscriber_name = ""

    async with guild_test_resource_guard(guild, bot_member=bot_member):
        hub_client = await ensure_hub_announcements_client(
            guild,
            bot,
            context,
            view_registry=PersistentViewRegistry(bot),
        )
        if hub_client is None:
            raise RuntimeError("Hub announcements client could not be ensured")

        mod_channel = resolve_network_announcements_channel(guild)
        if mod_channel is None:
            from bot.services.guild_layout import find_network_announcements_text_channel

            legacy = find_network_announcements_text_channel(
                guild,
                include_announcement=False,
            )
            if legacy is not None:
                raise RuntimeError(
                    f"{legacy.mention} is still a plain text channel after ensure — "
                    "run `/server init` with Manage Channels permission"
                )
            raise RuntimeError("#network-announcements channel missing after ensure")
        if not mod_channel.is_news():
            raise RuntimeError(
                "#network-announcements is not an announcement channel — run `/server init`"
            )

        subscriber_name, subscriber_subscribe_id = await _provision_smoke_subscriber(
            guild,
            bot,
            context,
            network_key=network_key,
        )
        await context.client_cache.load_cache()
        await context.routing_service.load_cache()

        network = await context.network_repo.get_by_key(network_key)
        if network is None:
            raise RuntimeError(f"Smoke network {network_key!r} not found after ensure")

        hub_sub = await context.client_repo.get_subscription(hub_client.id, network.id)
        if hub_sub is None:
            raise RuntimeError("Hub announcements subscription missing for smoke network")

        hub_publish = guild.get_channel(hub_sub.publish_channel_id)
        hub_subscribe = guild.get_channel(hub_sub.subscribe_channel_id)
        subscriber_subscribe = guild.get_channel(subscriber_subscribe_id)
        if not isinstance(hub_publish, discord.TextChannel):
            raise RuntimeError("Hub publish channel missing")
        if hub_subscribe is None:
            raise RuntimeError("Hub subscribe channel missing")
        if subscriber_subscribe is None:
            raise RuntimeError("Smoke subscriber subscribe channel missing")

        hub_before = len(
            await _recent_bot_text_messages(hub_subscribe, bot_user_id=bot_member.id)
        )
        sub_before = len(
            await _recent_bot_text_messages(
                subscriber_subscribe,
                bot_user_id=bot_member.id,
            )
        )

        token = secrets.token_hex(4)
        inject_body = f"Smoke hub inject {token}"
        sent = await inject_hub_announcement(hub_publish, content=inject_body)
        relay = await context.relay_service.relay_message(sent)
        if relay is None or not relay.success:
            reason = context.relay_service.feed_reject_reason(sent) or "relay failed"
            raise RuntimeError(f"Hub inject relay failed: {reason}")

        sub_after = await _recent_bot_text_messages(subscriber_subscribe, bot_user_id=bot_member.id)
        if len(sub_after) <= sub_before:
            raise RuntimeError("Subscriber subscribe channel did not receive hub relay")

        hub_after_inject = await _recent_bot_text_messages(hub_subscribe, bot_user_id=bot_member.id)
        if len(hub_after_inject) > hub_before:
            raise RuntimeError("Hub subscribe channel received inbound relay (write-only violated)")

        publisher = await context.client_repo.get_by_server_name(guild.id, subscriber_name)
        if publisher is None:
            raise RuntimeError("Smoke publisher client missing")
        pub_sub = await context.client_repo.get_subscription(publisher.id, hub_sub.network_id or 0)
        if pub_sub is None:
            raise RuntimeError("Smoke publisher subscription missing")

        pub_publish = guild.get_channel(pub_sub.publish_channel_id)
        if not isinstance(pub_publish, discord.TextChannel):
            raise RuntimeError("Smoke publisher publish channel missing")

        hub_before_publisher = len(
            await _recent_bot_text_messages(hub_subscribe, bot_user_id=bot_member.id)
        )
        pub_token = secrets.token_hex(4)
        pub_sent = await inject_hub_announcement(
            pub_publish,
            content=f"Smoke pub inject {pub_token}",
        )
        pub_relay = await context.relay_service.relay_message(pub_sent)
        if pub_relay is None or not pub_relay.success:
            raise RuntimeError("Publisher inject relay failed")

        hub_after_publisher = await _recent_bot_text_messages(
            hub_subscribe,
            bot_user_id=bot_member.id,
        )
        if len(hub_after_publisher) > hub_before_publisher:
            raise RuntimeError(
                "Hub subscribe channel received relay from another publisher (write-only violated)"
            )

        dispatch_token = secrets.token_hex(4)
        dispatch_message = await mod_channel.send(
            f"[{network_key}]\nSmoke mod dispatch {dispatch_token}",
        )
        dispatch = await dispatch_hub_announcement(bot, context, guild, dispatch_message)
        if not dispatch.networks_relayed:
            raise RuntimeError(
                "Mod channel dispatch failed: "
                + ("; ".join(dispatch.errors) if dispatch.errors else "no networks relayed")
            )
        if not await _channel_contains_token(hub_publish, dispatch_token):
            raise RuntimeError(
                "Mod channel dispatch did not appear on hub publish channel"
            )

        publish_token = secrets.token_hex(4)
        publish_body = f"Smoke announcement publish {publish_token}"
        await _ensure_channel_follow(mod_channel, hub_publish)
        publish_message = await mod_channel.send(publish_body)
        try:
            await publish_message.publish()
        except discord.HTTPException as exc:
            raise RuntimeError(
                f"Could not publish announcement from #network-announcements: {exc}"
            ) from exc
        if not await _wait_for_channel_token(hub_publish, publish_token):
            raise RuntimeError(
                "Published announcement did not arrive on hub publish channel "
                "via Channel Follow"
            )

        try:
            await cleanup_smoke_client(
                guild,
                context,
                server_name=subscriber_name,
                bot_member=bot_member,
            )
        finally:
            pass

        return HubAnnouncementsSmokeResult(
            hub_client_id=hub_client.id,
            subscriber_server_name=subscriber_name,
            network_key=network_key,
        )
