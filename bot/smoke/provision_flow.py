from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.config import Settings
from bot.core.models.errors import NetworkValidationError
from bot.core.models.server_request import ServerRequestStatus
from bot.core.networks.roles import (
    resolve_access_role,
)
from bot.core.runtime import BotContext
from bot.recipes.onboarding.service import ServerRequestService
from bot.smoke.constants import SMOKE_CLEANUP_REASON
from bot.smoke.permission_probe import (
    PROBE_PNG,
    verify_operator_permissions_live,
    verify_provision_permissions_live,
)
from bot.smoke.resource_guard import delete_guild_channel_for_cleanup, guild_test_resource_guard
from bot.testing.context_factory import create_bot_context
from bot.ui.persistent_views import PersistentViewRegistry

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.core.database.connection import Database

logger = logging.getLogger(__name__)

_PROBE_REASON = SMOKE_CLEANUP_REASON

_SMOKE_JOIN_REQUEST_PREFIXES = ("Smoke Accept ", "Smoke Deny ", "Smoke Rebuild ")


def _is_smoke_server_name(server_name: str) -> bool:
    return server_name.startswith(_SMOKE_JOIN_REQUEST_PREFIXES)


def _is_smoke_join_request_message(
    message: discord.Message,
    bot_member: discord.Member,
) -> bool:
    if message.author.id != bot_member.id or not message.embeds:
        return False
    embed = message.embeds[0]
    for field in embed.fields:
        if (field.name or "").casefold() != "name":
            continue
        return _is_smoke_server_name((field.value or "").strip())
    return False


async def _delete_join_request_message(
    channel: discord.TextChannel,
    message: discord.Message,
) -> None:
    try:
        await message.delete()
        return
    except discord.NotFound:
        return
    except discord.HTTPException:
        pass
    try:
        await channel.delete_messages([message])
    except discord.HTTPException:
        logger.warning(
            "Smoke cleanup: could not delete join-request message",
            extra={"channel_id": channel.id, "message_id": message.id},
        )


async def _delete_smoke_channel_object(
    channel: discord.abc.GuildChannel,
    *,
    reason: str,
    bot_member: discord.Member | None = None,
) -> None:
    await delete_guild_channel_for_cleanup(
        channel,
        reason=reason,
        bot_member=bot_member,
        delete_webhooks=True,
    )


async def _delete_smoke_channel(
    guild: discord.Guild,
    channel_id: int,
    *,
    reason: str,
    bot_member: discord.Member | None = None,
) -> None:
    channel_obj: discord.abc.GuildChannel | None = guild.get_channel(channel_id)
    if channel_obj is None:
        try:
            fetched = await guild.fetch_channel(channel_id)
        except discord.NotFound:
            return
        except discord.Forbidden:
            return
        if not isinstance(fetched, discord.abc.GuildChannel):
            return
        channel_obj = fetched

    await _delete_smoke_channel_object(
        channel_obj,
        reason=reason,
        bot_member=bot_member,
    )


@dataclass(frozen=True)
class GuildInitSmokeResult:
    operator_steps: tuple[str, ...]
    provision_steps: tuple[str, ...]


@dataclass(frozen=True)
class SmokeProbeResult:
    steps: tuple[str, ...]


@dataclass(frozen=True)
class SmokeFlowResult:
    accepted_request_id: int
    denied_request_id: int
    profile_channel_id: int
    publish_channel_id: int | None = None


class _SmokeProfileAttachment:
    filename = "smoke-profile.png"
    content_type: str | None = "image/png"
    url = "https://cdn.discordapp.com/attachments/0/0/smoke-profile.png"

    def __init__(self, data: bytes) -> None:
        self.size = len(data)
        self._data = data

    async def read(self) -> bytes:
        return self._data


async def run_guild_init_smoke_checks(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    *,
    access_role_name: str,
    operator_role_name: str,
) -> GuildInitSmokeResult:
    """Permission + provision smoke run at the start of `/server init`."""
    operator_steps = await verify_operator_permissions_live(
        guild,
        bot_member,
        access_role,
        operator_role_name=operator_role_name,
    )
    from bot.smoke.pacing import pause_between_probe_phases

    await pause_between_probe_phases()
    provision_steps = await verify_provision_permissions_live(
        guild,
        bot_member,
        access_role,
        access_role_name=access_role_name,
        operator_role_name=operator_role_name,
    )
    return GuildInitSmokeResult(
        operator_steps=tuple(operator_steps),
        provision_steps=tuple(provision_steps),
    )


async def run_pre_init_provision_probe(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> SmokeProbeResult:
    """CLI wrapper — provision path only (legacy --probe-only scripts)."""
    access_role = resolve_access_role(guild, role_name=settings.network_access_role_name)
    steps = await verify_provision_permissions_live(
        guild,
        bot_member,
        access_role,
        access_role_name=settings.network_access_role_name,
        operator_role_name=settings.network_operator_role_name,
    )
    return SmokeProbeResult(steps=tuple(steps))


async def run_pre_init_smoke_checks(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> GuildInitSmokeResult:
    """CLI wrapper — same checks `/server init` runs before hub setup."""
    access_role = resolve_access_role(guild, role_name=settings.network_access_role_name)
    return await run_guild_init_smoke_checks(
        guild,
        bot_member,
        access_role,
        access_role_name=settings.network_access_role_name,
        operator_role_name=settings.network_operator_role_name,
    )


async def run_post_init_join_smoke(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
) -> str | None:
    """Submit → accept → deny smoke after hub channels exist. Returns a note or None."""
    from bot.core.hub.resolve import resolve_join_requests_channel

    if resolve_join_requests_channel(guild) is None:
        raise NetworkValidationError(
            "Join-approval smoke failed: `#join-requests` was not found after guild init."
        )

    try:
        flow = await run_join_approval_smoke_flow(guild, bot, context)
    except RuntimeError as exc:
        raise NetworkValidationError(f"Join-approval smoke failed:\n• {exc}") from exc

    publish_note = (
        f", publish_channel_id={flow.publish_channel_id}"
        if flow.publish_channel_id is not None
        else ""
    )
    return (
        "Join-approval smoke passed "
        f"(accept #{flow.accepted_request_id}, deny #{flow.denied_request_id}"
        f"{publish_note})."
    )


async def create_smoke_context(
    settings: Settings,
) -> tuple[Database, BotContext]:
    return await create_bot_context(settings)


async def cleanup_smoke_client(
    guild: discord.Guild,
    context: BotContext,
    *,
    server_name: str,
    bot_member: discord.Member,
) -> None:
    """Remove Discord resources and DB row for a smoke-provisioned client."""
    client = await context.store.clients.get_by_server_name(guild.id, server_name)
    if client is None:
        return

    subscriptions = await context.store.clients.list_subscriptions_by_client(client.id)
    channel_ids: set[int] = {client.profile_channel_id}
    for subscription in subscriptions:
        channel_ids.add(subscription.publish_channel_id)
        channel_ids.add(subscription.subscribe_channel_id)

    if client.emoji_id is not None:
        emoji = guild.get_emoji(client.emoji_id)
        if emoji is not None:
            try:
                await emoji.delete(reason=_PROBE_REASON)
            except discord.HTTPException:
                logger.warning("Smoke cleanup: could not delete client emoji")

    client_role = guild.get_role(client.client_role_id)
    if client_role is None:
        try:
            client_role = await guild.fetch_role(client.client_role_id)
        except (discord.NotFound, discord.Forbidden):
            client_role = None
    if client_role is not None and client_role in bot_member.roles:
        try:
            await bot_member.remove_roles(client_role, reason=_PROBE_REASON)
        except discord.HTTPException:
            logger.warning("Smoke cleanup: could not remove client role from bot member")

    category = guild.get_channel(client.category_id)
    if not isinstance(category, discord.CategoryChannel):
        try:
            fetched = await guild.fetch_channel(client.category_id)
        except (discord.NotFound, discord.Forbidden):
            fetched = None
        category = fetched if isinstance(fetched, discord.CategoryChannel) else None

    # Delete every channel in the category first. Bot access is inherited from the
    # category; deleting the category early orphans channels the bot cannot reach.
    if isinstance(category, discord.CategoryChannel):
        for channel in list(category.channels):
            await _delete_smoke_channel_object(
                channel,
                reason=_PROBE_REASON,
                bot_member=bot_member,
            )
        if category.channels:
            logger.warning(
                "Smoke cleanup: client category still has channels; skipping category delete",
                extra={"category_id": category.id, "remaining": len(category.channels)},
            )
        else:
            try:
                await category.delete(reason=_PROBE_REASON)
            except discord.HTTPException:
                logger.warning("Smoke cleanup: could not delete client category")
            category = None

    for channel_id in channel_ids:
        await _delete_smoke_channel(
            guild,
            channel_id,
            reason=_PROBE_REASON,
            bot_member=bot_member,
        )

    if client_role is not None:
        try:
            await client_role.delete(reason=_PROBE_REASON)
        except discord.HTTPException:
            logger.warning("Smoke cleanup: could not delete client role")

    await context.store.clients.delete_with_relations(client.id)
    await context.refresh_projections()


async def cleanup_smoke_join_request_messages(
    guild: discord.Guild,
    context: BotContext,
    request_ids: list[int],
) -> None:
    """Remove `#join-requests` review messages and DB rows left by init smoke tests."""
    if not request_ids:
        return

    from bot.core.hub.resolve import resolve_join_requests_channel

    channel = resolve_join_requests_channel(guild)
    for request_id in request_ids:
        request = await context.store.requests.get_by_id(request_id)
        if request is None:
            continue
        if channel is not None and request.moderator_message_id is not None:
            try:
                message = await channel.fetch_message(request.moderator_message_id)
                await _delete_join_request_message(channel, message)
            except discord.NotFound:
                pass
            except discord.HTTPException:
                logger.warning(
                    "Smoke cleanup: could not fetch join-request message",
                    extra={
                        "request_id": request_id,
                        "message_id": request.moderator_message_id,
                    },
                )
        await context.store.requests.delete_by_id(request_id)


async def cleanup_join_requests_smoke_artifacts(
    guild: discord.Guild,
    context: BotContext,
    bot_member: discord.Member,
) -> None:
    """Remove smoke join-request messages and DB rows from `#join-requests`."""
    from bot.core.hub.resolve import resolve_join_requests_channel

    channel = resolve_join_requests_channel(guild)
    if channel is not None:
        try:
            async for message in channel.history(limit=200):
                if not _is_smoke_join_request_message(message, bot_member):
                    continue
                await _delete_join_request_message(channel, message)
        except discord.HTTPException as exc:
            logger.warning(
                "Smoke cleanup: could not scan join-requests channel",
                extra={"channel_id": channel.id, "error": str(exc)},
            )

    for prefix in _SMOKE_JOIN_REQUEST_PREFIXES:
        for request in await context.store.requests.list_by_server_name_prefix(prefix):
            await context.store.requests.delete_by_id(request.id)


async def cleanup_all_hub_rebuild_smoke_clients(
    guild: discord.Guild,
    context: BotContext,
    bot_member: discord.Member,
) -> list[str]:
    """Remove every hub-rebuild smoke client from Discord and the database."""
    from bot.smoke.resource_guard import (
        cleanup_hub_rebuild_smoke_artifacts,
        cleanup_orphan_smoke_subscription_channels,
    )

    rebuild_clients = [
        client
        for client in await context.store.clients.list_all()
        if client.server_name.startswith("Smoke Rebuild ")
    ]
    for client in rebuild_clients:
        await cleanup_smoke_client(
            guild,
            context,
            server_name=client.server_name,
            bot_member=bot_member,
        )
    await cleanup_hub_rebuild_smoke_artifacts(guild, bot_member)
    return await cleanup_orphan_smoke_subscription_channels(guild, context)


async def run_join_approval_smoke_flow(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
) -> SmokeFlowResult:
    """Exercise submit → accept → network subscribe → webhook probe → cleanup → deny."""
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")

    async with guild_test_resource_guard(guild, bot_member=bot_member):
        await cleanup_join_requests_smoke_artifacts(guild, context, bot_member)
        service = ServerRequestService(context, bot, view_registry=PersistentViewRegistry(bot))
        suffix = secrets.token_hex(3)
        accept_server_name = f"Smoke Accept {suffix}"
        deny_server_name = f"Smoke Deny {suffix}"
        attachment = _SmokeProfileAttachment(PROBE_PNG)
        accept_request_id = 0
        profile_channel_id = 0
        publish_channel_id: int | None = None
        request_ids_for_cleanup: list[int] = []

        try:
            # Bot acts as requester to exercise provisioning; outcome DMs are skipped for self.
            submit_accept = await service.submit_request(
                guild,
                requester=bot_member,
                server_name=accept_server_name,
                display_name=f"Smoke Accept {suffix[:6]}",
                profile_image=attachment,
            )
            if not submit_accept.success:
                raise RuntimeError(f"Smoke submit (accept path) failed: {submit_accept.error}")

            pending = await context.store.requests.get_pending_for_requester(bot_member.id)
            if pending is None:
                raise RuntimeError("Smoke submit did not create a pending request.")
            accept_request_id = pending.id
            request_ids_for_cleanup.append(accept_request_id)

            approve = await service.approve_request(
                guild,
                request_id=accept_request_id,
                moderator=bot_member,
            )
            if not approve.success:
                raise RuntimeError(f"Smoke accept failed: {approve.error}")

            client = await context.store.clients.get_by_server_name(guild.id, accept_server_name)
            if client is None:
                raise RuntimeError("Smoke accept did not register a client.")

            if "Leaders access sync reported issues" in (approve.message or ""):
                raise RuntimeError(
                    f"Smoke accept Leaders sync failed: {approve.message}",
                )

            client_role = guild.get_role(client.client_role_id)
            if client_role is None:
                raise RuntimeError("Smoke accept client role is missing from the guild.")

            from bot.smoke.server_init_probes import _collect_leaders_access_gaps

            leaders_gaps = [
                gap
                for gap in await _collect_leaders_access_gaps(guild, context)
                if accept_server_name in gap
            ]
            if leaders_gaps:
                raise RuntimeError(
                    "Smoke accept did not grant Leaders access: " + "; ".join(leaders_gaps),
                )

            profile_channel_id = client.profile_channel_id
            channel = guild.get_channel(profile_channel_id)
            if channel is None:
                raise RuntimeError("Smoke accept profile channel is missing from the guild.")

            if client_role is not None and client_role in bot_member.roles:
                guard_role = client_role
            else:
                guard_role = None

            networks = await context.store.networks.list_all()
            if networks:
                from bot.core.clients.subscription import ClientSubscriptionService

                network = networks[0]
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
                        f"Smoke network subscribe failed: {subscribe.error or 'unknown error'}"
                    )

                publish_channel_id = subscribe.subscription.publish_channel_id
                publish_channel = guild.get_channel(publish_channel_id)
                if not isinstance(publish_channel, discord.TextChannel):
                    raise RuntimeError("Smoke publish channel is missing from the guild.")

                if guard_role is None or guard_role not in bot_member.roles:
                    raise RuntimeError(
                        "Smoke client role was not assigned to the bot member after approval."
                    )

                webhook = await publish_channel.create_webhook(
                    name=f"smoke-wh-{suffix}"[:32],
                    reason=_PROBE_REASON,
                )
                await webhook.delete(reason=_PROBE_REASON)

            await cleanup_smoke_client(
                guild,
                context,
                server_name=accept_server_name,
                bot_member=bot_member,
            )

            submit_deny = await service.submit_request(
                guild,
                requester=bot_member,
                server_name=deny_server_name,
                display_name=f"Smoke Deny {suffix[:6]}",
                profile_image=attachment,
            )
            if not submit_deny.success:
                raise RuntimeError(f"Smoke submit (deny path) failed: {submit_deny.error}")

            pending_deny = await context.store.requests.get_pending_for_requester(bot_member.id)
            if pending_deny is None:
                raise RuntimeError("Smoke deny-path submit did not create a pending request.")
            request_ids_for_cleanup.append(pending_deny.id)

            deny = await service.deny_request(
                request_id=pending_deny.id,
                moderator=bot_member,
            )
            if not deny.success:
                raise RuntimeError(f"Smoke deny failed: {deny.error}")

            resolved = await context.store.requests.get_by_id(pending_deny.id)
            if resolved is None or resolved.status != ServerRequestStatus.DENIED:
                raise RuntimeError("Smoke deny did not resolve the request.")

            return SmokeFlowResult(
                accepted_request_id=accept_request_id,
                denied_request_id=pending_deny.id,
                profile_channel_id=profile_channel_id,
                publish_channel_id=publish_channel_id,
            )
        except Exception:
            await cleanup_smoke_client(
                guild,
                context,
                server_name=accept_server_name,
                bot_member=bot_member,
            )
            raise
        finally:
            await cleanup_smoke_join_request_messages(
                guild,
                context,
                request_ids_for_cleanup,
            )
            await cleanup_join_requests_smoke_artifacts(guild, context, bot_member)


async def ensure_smoke_network_key(
    context: BotContext,
    bot: NetworkRelayBot,
    guild: discord.Guild,
    *,
    default_key: str = "smoke",
) -> str:
    """Return a network key for subscribe/rebuild smokes, creating one if needed."""
    explicit = os.environ.get("SMOKE_NETWORK_KEY", "").strip().lower()
    if explicit:
        existing = await context.store.networks.get_by_key(explicit)
        if existing is None:
            from bot.recipes.network.service import create_network
            from bot.ui.persistent_views import PersistentViewRegistry

            created = await create_network(
                context,
                bot,
                guild,
                key=explicit,
                display_name=explicit.title(),
                view_registry=PersistentViewRegistry(bot),
            )
            if not created.success or created.network is None:
                raise RuntimeError(created.error or f"could not create network {explicit!r}")
        return explicit

    networks = await context.store.networks.list_all()
    if networks:
        return networks[0].key

    from bot.recipes.network.service import create_network
    from bot.ui.persistent_views import PersistentViewRegistry

    created = await create_network(
        context,
        bot,
        guild,
        key=default_key,
        display_name=default_key.title(),
        view_registry=PersistentViewRegistry(bot),
    )
    if not created.success or created.network is None:
        raise RuntimeError(created.error or f"could not create network {default_key!r}")
    return created.network.key


def resolve_smoke_network_key(context: BotContext) -> str:
    explicit = os.environ.get("SMOKE_NETWORK_KEY", "").strip().lower()
    if explicit:
        return explicit
    raise RuntimeError(
        "Set SMOKE_NETWORK_KEY to a network nkey for network-subscribe smoke, "
        "or run ensure_smoke_network_key() first."
    )


@dataclass(frozen=True)
class HubRebuildSmokeState:
    client_id: int
    category_id: int
    profile_channel_id: int
    publish_channel_id: int
    subscribe_channel_id: int
    client_role_id: int
    network_key: str
    server_name: str


async def provision_smoke_client_with_subscription(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    *,
    network_key: str,
    network_display_name: str | None = None,
) -> HubRebuildSmokeState:
    """Create a smoke client subscribed to ``network_key`` without cleaning up."""
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")

    network = await context.store.networks.get_by_key(network_key)
    if network is None:
        network = await context.store.networks.create(
            guild_id=guild.id,
            key=network_key,
            display_name=network_display_name or network_key.title(),
        )
        await context.refresh_network_counts()

    suffix = secrets.token_hex(3)
    server_name = f"Smoke Rebuild {suffix}"
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
        display_name=f"Smoke Rebuild {suffix[:6]}",
        profile_image=attachment,
    )
    if not submit.success:
        raise RuntimeError(f"Smoke submit failed: {submit.error}")

    pending = await context.store.requests.get_pending_for_requester(bot_member.id)
    if pending is None:
        raise RuntimeError("Smoke submit did not create a pending request.")

    approve = await service.approve_request(
        guild,
        request_id=pending.id,
        moderator=bot_member,
    )
    if not approve.success:
        raise RuntimeError(f"Smoke accept failed: {approve.error}")

    client = await context.store.clients.get_by_server_name(guild.id, server_name)
    if client is None:
        raise RuntimeError("Smoke accept did not register a client.")

    from bot.core.clients.subscription import ClientSubscriptionService

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
        raise RuntimeError(f"Smoke network subscribe failed: {subscribe.error or 'unknown error'}")

    return HubRebuildSmokeState(
        client_id=client.id,
        category_id=client.category_id,
        profile_channel_id=client.profile_channel_id,
        publish_channel_id=subscribe.subscription.publish_channel_id,
        subscribe_channel_id=subscribe.subscription.subscribe_channel_id,
        client_role_id=client.client_role_id,
        network_key=network.key,
        server_name=server_name,
    )


async def run_hub_rebuild_smoke_flow(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    *,
    skip_cleanup: bool = False,
) -> HubRebuildSmokeState:
    """Provision client, uninit hub, init hub, recreate network, verify relink."""
    from bot.core.hub.data_reset import reset_hub_layout_data
    from bot.core.hub.resolve import resolve_join_requests_channel
    from bot.recipes.hub.initialize import initialize_guild
    from bot.recipes.hub.uninitialize import uninitialize_guild
    from bot.recipes.network.service import create_network
    from bot.ui.persistent_views import PersistentViewRegistry

    view_registry = PersistentViewRegistry(bot)

    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")

    network_key = resolve_smoke_network_key(context)

    await cleanup_all_hub_rebuild_smoke_clients(guild, context, bot_member)

    if resolve_join_requests_channel(guild) is None:
        clients = await context.store.clients.list_all()
        bootstrap = await initialize_guild(
            guild,
            bot_member,
            access_role_name=bot.settings.network_access_role_name,
            operator_role_name=bot.settings.network_operator_role_name,
            clients=clients,
            bot=bot,
            context=context,
            skip_join_smoke=True,
            view_registry=view_registry,
        )
        if not bootstrap.success:
            raise RuntimeError(bootstrap.reason or "hub bootstrap init failed")

    state = await provision_smoke_client_with_subscription(
        guild,
        bot,
        context,
        network_key=network_key,
    )

    try:
        uninit = await uninitialize_guild(
            guild,
            bot_member,
            access_role_name=bot.settings.network_access_role_name,
            operator_role_name=bot.settings.network_operator_role_name,
        )
        if not uninit.success:
            raise RuntimeError(uninit.reason or "server uninit failed")

        from bot.core.layout.managed import hub_category_names, preserved_channel_names

        # Client artifacts must survive hub uninit.
        if guild.get_role(state.client_role_id) is None:
            raise RuntimeError("Client role was deleted during hub uninit.")
        if not isinstance(guild.get_channel(state.category_id), discord.CategoryChannel):
            raise RuntimeError("Client category was deleted during hub uninit.")
        if not isinstance(guild.get_channel(state.profile_channel_id), discord.TextChannel):
            raise RuntimeError("Client profile channel was deleted during hub uninit.")
        if not isinstance(guild.get_channel(state.publish_channel_id), discord.TextChannel):
            raise RuntimeError("Client publish channel was deleted during hub uninit.")
        if not isinstance(
            guild.get_channel(state.subscribe_channel_id),
            discord.TextChannel,
        ):
            raise RuntimeError("Client subscribe channel was deleted during hub uninit.")

        remaining_hub_cats = [
            cat.name for cat in guild.categories if cat.name.casefold() in hub_category_names()
        ]
        if remaining_hub_cats:
            raise RuntimeError(
                "Hub categories still present after uninit: " + ", ".join(remaining_hub_cats)
            )
        for preserved in preserved_channel_names():
            # Community/preserved channels may remain; never treat as failure if present.
            _ = preserved

        await reset_hub_layout_data(context, guild.id)

        client = await context.store.clients.get_by_id(state.client_id)
        if client is None:
            raise RuntimeError("Smoke client disappeared from database after hub reset.")

        clients = await context.store.clients.list_all()
        init = await initialize_guild(
            guild,
            bot_member,
            access_role_name=bot.settings.network_access_role_name,
            operator_role_name=bot.settings.network_operator_role_name,
            clients=clients,
            bot=bot,
            context=context,
            skip_join_smoke=True,
            view_registry=view_registry,
        )
        if not init.success:
            raise RuntimeError(init.reason or "server init failed")

        create = await create_network(
            context,
            bot,
            guild,
            key=state.network_key,
            display_name=state.network_key.title(),
            view_registry=view_registry,
        )
        if not create.success or create.network is None:
            raise RuntimeError(create.error or "network recreate failed")

        subscription = await context.store.clients.get_subscription(
            state.client_id,
            create.network.id,
        )
        if subscription is None:
            raise RuntimeError("Subscription was not relinked after network recreate.")

        if subscription.publish_channel_id != state.publish_channel_id:
            raise RuntimeError(
                "Publish channel id changed after rebuild: "
                f"{state.publish_channel_id} -> {subscription.publish_channel_id}"
            )
        if subscription.subscribe_channel_id != state.subscribe_channel_id:
            raise RuntimeError(
                "Subscribe channel id changed after rebuild: "
                f"{state.subscribe_channel_id} -> {subscription.subscribe_channel_id}"
            )

        client_role = guild.get_role(state.client_role_id)
        if client_role is None:
            try:
                client_role = await guild.fetch_role(state.client_role_id)
            except discord.NotFound:
                client_role = None
        if client_role is None:
            from bot.core.clients.names import build_client_role_name

            refreshed = await context.store.clients.get_by_id(state.client_id)
            expected_name = (
                build_client_role_name(refreshed.server_name) if refreshed is not None else None
            )
            if expected_name is not None:
                client_role = discord.utils.get(guild.roles, name=expected_name)
            if client_role is None:
                raise RuntimeError(
                    "Client role was removed during hub rebuild "
                    f"(role_id={state.client_role_id}, expected_name={expected_name!r}, "
                    f"uninit_deleted_roles={uninit.deleted_roles})."
                )

        category = guild.get_channel(state.category_id)
        if not isinstance(category, discord.CategoryChannel):
            try:
                fetched = await guild.fetch_channel(state.category_id)
            except discord.NotFound:
                fetched = None
            category = fetched if isinstance(fetched, discord.CategoryChannel) else None
        if category is None:
            raise RuntimeError("Client category was removed during hub rebuild.")

        # Client layout overwrites must match YAML after re-init.
        from bot.core.clients.names import slugify_client_name
        from bot.core.hub.resolve import resolve_human_moderator_role
        from bot.core.layout import LayoutContext, compile_client
        from bot.core.networks.roles import (
            resolve_access_role,
            resolve_operator_role_by_name,
        )

        access = resolve_access_role(
            guild,
            role_name=bot.settings.network_access_role_name,
        )
        operator = resolve_operator_role_by_name(
            guild,
            role_name=bot.settings.network_operator_role_name,
        )
        layout_ctx = LayoutContext(
            guild=guild,
            bot_member=bot_member,
            access_role=access,
            moderator_role=resolve_human_moderator_role(guild),
            operator_role=operator,
            client_role=client_role,
            server_name=state.server_name,
            slug=slugify_client_name(state.server_name),
            network_key=state.network_key,
            reason="hub rebuild smoke",
        )
        desired_cat = next(
            r.overwrites
            for r in compile_client(layout_ctx, channel_ids={"client"})
            if r.id == "client"
        ).get(client_role)
        if desired_cat is not None:
            current = category.overwrites_for(client_role)
            if (
                current.pair()[0].value != desired_cat.pair()[0].value
                or current.pair()[1].value != desired_cat.pair()[1].value
            ):
                raise RuntimeError(
                    "Client category overwrites do not match compile_client after re-init."
                )

        if (
            context.routing_service.resolve_publish_subscription(
                state.publish_channel_id,
            )
            is None
        ):
            raise RuntimeError("Routing cache does not resolve smoke publish channel.")

        return state
    finally:
        if not skip_cleanup:
            manual = await cleanup_all_hub_rebuild_smoke_clients(guild, context, bot_member)
            if manual:
                print(
                    f"WARN: {len(manual)} channel(s) need manual deletion in Discord "
                    "(Server Settings → Channels):",
                    flush=True,
                )
                for item in manual:
                    print(f"  - {item}", flush=True)


async def run_hub_onboard_smoke_flow(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
) -> SmokeFlowResult:
    """Baseline: join-approval smoke with optional network subscribe."""
    return await run_join_approval_smoke_flow(guild, bot, context)
