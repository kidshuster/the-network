from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.app.widgets import PersistentViewRegistry
from bot.core.clients.setup_state import resolve_setup_state
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.network import Network
from bot.features.channels.stickies.subscription import (
    _maybe_post_activation_welcome,
    sync_subscription_setup,
)
from bot.features.recipes.hub.clients.subscription import (
    ensure_client_publish_channels,
    strip_client_publish_channels,
)
from bot.features.recipes.hub.onboarding.service import ServerRequestService
from tests.core.permission_probe import PROBE_PNG
from tests.core.provision_flow import (
    _SmokeProfileAttachment,
    cleanup_smoke_client,
    ensure_smoke_network_key,
)
from tests.core.resource_guard import guild_test_resource_guard
from tests.core.setup_welcome_probes import _bot_messages_with_footer

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot
    from bot.app.context import BotContext

logger = logging.getLogger(__name__)

_SMOKE_READONLY_PREFIX = "Smoke Readonly "
_ACTIVATION_FOOTER = "server connected"


@dataclass(frozen=True)
class ClientReadOnlySmokeResult:
    server_name: str
    network_key: str


async def _provision_smoke_readonly_client(
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
    server_name = f"{_SMOKE_READONLY_PREFIX}{suffix}"
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
        display_name=f"Smoke RO {suffix[:6]}",
        profile_image=attachment,
    )
    if not submit.success:
        raise RuntimeError(f"Smoke read-only submit failed: {submit.error}")

    pending = await context.store.requests.get_pending_for_requester(bot_member.id)
    if pending is None:
        raise RuntimeError("Smoke read-only submit did not create a pending request.")

    approve = await service.approve_request(
        guild,
        request_id=pending.id,
        moderator=bot_member,
    )
    if not approve.success:
        raise RuntimeError(f"Smoke read-only accept failed: {approve.error}")

    client = await context.store.clients.get_by_server_name(guild.id, server_name)
    if client is None:
        raise RuntimeError("Smoke read-only accept did not register a client.")

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
        raise RuntimeError(
            f"Smoke read-only subscribe failed: {subscribe.error or 'unknown error'}"
        )

    await context.store.requests.delete_by_id(pending.id)
    return client, subscribe.subscription


async def cleanup_smoke_readonly_clients(
    guild: discord.Guild,
    context: BotContext,
    bot_member: discord.Member,
) -> None:
    for client in await context.store.clients.list_all():
        if client.guild_id != guild.id:
            continue
        if not client.server_name.startswith(_SMOKE_READONLY_PREFIX):
            continue
        await cleanup_smoke_client(
            guild,
            context,
            server_name=client.server_name,
            bot_member=bot_member,
        )


async def run_client_read_only_smoke_flow(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
) -> ClientReadOnlySmokeResult:
    """Toggle read-only: strip/restore publish; Active via subscribe; no welcome spam."""
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")

    network_key = await ensure_smoke_network_key(context, bot, guild)
    network = await context.store.networks.get_by_key(network_key)
    if network is None:
        raise RuntimeError(f"Smoke network {network_key!r} was not found.")

    view_registry = PersistentViewRegistry(bot)
    async with guild_test_resource_guard(guild, bot_member=bot_member):
        await cleanup_smoke_readonly_clients(guild, context, bot_member)
        client: Client | None = None
        server_name = ""
        try:
            client, subscription = await _provision_smoke_readonly_client(
                guild,
                bot,
                context,
                network=network,
            )
            server_name = client.server_name
            if not subscription.publish_channel_id:
                raise RuntimeError("Expected publish channel after normal subscribe.")
            publish_before = guild.get_channel(subscription.publish_channel_id)
            if publish_before is None:
                raise RuntimeError("Publish channel missing after subscribe.")

            client = await context.store.clients.set_read_only(client.id, True)
            await strip_client_publish_channels(
                guild,
                client=client,
                client_repo=context.store.clients,
            )
            refreshed = await context.store.clients.get_subscription_by_id(subscription.id)
            if refreshed is None:
                raise RuntimeError("Subscription missing after read-only strip.")
            subscription = refreshed
            if subscription.publish_channel_id is not None:
                raise RuntimeError("publish_channel_id should be cleared in read-only mode.")
            if guild.get_channel(publish_before.id) is not None:
                raise RuntimeError("Publish channel should be deleted in read-only mode.")

            subscription = await context.store.clients.set_subscribe_confirmed(
                subscription.id,
                True,
            )
            state = await resolve_setup_state(
                guild,
                subscription,
                network_active=network.enabled,
                read_only=True,
            )
            if not state.fully_configured or state.link_status != "Active":
                raise RuntimeError(
                    "Read-only setup should be Active once subscribe is confirmed "
                    f"(state={state})."
                )

            subscribe_channel = guild.get_channel(subscription.subscribe_channel_id)
            if subscribe_channel is None:
                raise RuntimeError("Subscribe channel missing during read-only smoke.")
            subscription = await _maybe_post_activation_welcome(
                bot,
                subscription,
                subscribe_channel=subscribe_channel,
                context=context,
                guild=guild,
                network=network,
                client=client,
                setup_state=state,
            )
            bot_user_id = bot.user.id if bot.user is not None else 0
            welcomes_before = await _bot_messages_with_footer(
                subscribe_channel,
                bot_user_id=bot_user_id,
                footer_marker=_ACTIVATION_FOOTER,
            )
            if len(welcomes_before) != 1:
                raise RuntimeError(
                    "Expected one activation welcome after first read-only activation "
                    f"(found {len(welcomes_before)})."
                )

            client = await context.store.clients.set_read_only(client.id, False)
            await ensure_client_publish_channels(
                guild,
                bot_member,
                client=client,
                client_repo=context.store.clients,
                network_repo=context.store.networks,
                access_role_name=bot.settings.network_access_role_name,
            )
            restored = await context.store.clients.get_subscription_by_id(subscription.id)
            if restored is None or restored.publish_channel_id is None:
                raise RuntimeError("Publish channel was not restored after leaving read-only.")
            subscription = restored
            publish_id = restored.publish_channel_id
            if guild.get_channel(publish_id) is None:
                raise RuntimeError("Restored publish channel id is missing in Discord.")

            await sync_subscription_setup(
                bot,
                context,
                guild,
                client=client,
                subscription=subscription,
                network=network,
                setup_mode="reconcile",
                view_registry=view_registry,
            )
            welcomes_after = await _bot_messages_with_footer(
                subscribe_channel,
                bot_user_id=bot_user_id,
                footer_marker=_ACTIVATION_FOOTER,
            )
            if len(welcomes_after) != len(welcomes_before):
                raise RuntimeError(
                    "Leaving read-only must not resend activation welcome "
                    f"(before={len(welcomes_before)} after={len(welcomes_after)})."
                )
            return ClientReadOnlySmokeResult(
                server_name=server_name,
                network_key=network_key,
            )
        finally:
            await cleanup_smoke_readonly_clients(guild, context, bot_member)
