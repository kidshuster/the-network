from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.domain.network import Network
from bot.services.subscription_setup import SubscriptionSetupState
from bot.services.subscription_setup_sticky import (
    _maybe_post_activation_welcome,
    sync_subscription_setup,
)
from bot.smoke.provision_flow import (
    _SmokeProfileAttachment,
    cleanup_smoke_client,
    ensure_smoke_network_key,
)
from bot.smoke.resource_guard import guild_test_resource_guard
from bot.services.permission_probe import PROBE_PNG
from bot.services.server_request_service import ServerRequestService

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

_SMOKE_WELCOME_PREFIX = "Smoke Welcome "
_ACTIVATION_FOOTER = "server connected"
_MEMBER_FOOTER = "network welcome"
_SUBSCRIBE_SETUP_FOOTER = "subscribe setup"
_PUBLISH_SETUP_FOOTER = "publish setup"
_DESKTOP_NOTE = "Discord desktop app"
_HISTORY_LIMIT = 50


@dataclass(frozen=True)
class SetupWelcomeSmokeResult:
    incumbent_server_name: str
    joiner_server_name: str
    network_key: str


def _embed_blob(message: discord.Message) -> str:
    parts: list[str] = []
    for embed in message.embeds:
        parts.extend([embed.title or "", embed.description or ""])
        for field in embed.fields:
            parts.append(field.value or "")
        if embed.footer and embed.footer.text:
            parts.append(embed.footer.text)
    return "\n".join(parts)


async def _bot_messages_with_footer(
    channel: discord.abc.GuildChannel,
    *,
    bot_user_id: int,
    footer_marker: str,
    limit: int = _HISTORY_LIMIT,
) -> list[discord.Message]:
    if not hasattr(channel, "history"):
        return []
    marker = footer_marker.casefold()
    matches: list[discord.Message] = []
    try:
        async for message in channel.history(limit=limit):
            if message.author.id != bot_user_id or not message.embeds:
                continue
            footer = (message.embeds[0].footer.text or "").casefold()
            if marker in footer:
                matches.append(message)
    except discord.HTTPException:
        logger.warning(
            "Setup welcome smoke: could not scan channel history",
            extra={"channel_id": getattr(channel, "id", None)},
        )
    return matches


async def _provision_smoke_welcome_client(
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
    server_name = f"{_SMOKE_WELCOME_PREFIX}{suffix}"
    service = ServerRequestService(context, bot)
    if not hasattr(bot, "get_guild"):
        bot.get_guild = lambda guild_id: guild if guild.id == guild_id else None  # type: ignore[attr-defined]

    stale = await context.server_request_repo.get_pending_for_requester(bot_member.id)
    if stale is not None:
        await service.deny_request(request_id=stale.id, moderator=bot_member)

    attachment = _SmokeProfileAttachment(PROBE_PNG)
    submit = await service.submit_request(
        guild,
        requester=bot_member,
        server_name=server_name,
        display_name=f"Smoke Welcome {suffix[:6]}",
        profile_image=attachment,
    )
    if not submit.success:
        raise RuntimeError(f"Smoke welcome submit failed: {submit.error}")

    pending = await context.server_request_repo.get_pending_for_requester(bot_member.id)
    if pending is None:
        raise RuntimeError("Smoke welcome submit did not create a pending request.")

    approve = await service.approve_request(
        guild,
        request_id=pending.id,
        moderator=bot_member,
    )
    if not approve.success:
        raise RuntimeError(f"Smoke welcome accept failed: {approve.error}")

    client = await context.client_repo.get_by_server_name(guild.id, server_name)
    if client is None:
        raise RuntimeError("Smoke welcome accept did not register a client.")

    from bot.services.client_subscription import ClientSubscriptionService

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
            f"Smoke welcome subscribe failed: {subscribe.error or 'unknown error'}"
        )

    await context.server_request_repo.delete_by_id(pending.id)
    return client, subscribe.subscription


async def verify_setup_sticky_copy(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    *,
    client: Client,
    subscription: ClientSubscription,
    network: Network,
) -> None:
    """Live check that setup stickies mention the uniform channel name and desktop follow note."""
    bot_user_id = bot.user.id if bot.user is not None else 0
    if bot_user_id == 0:
        raise RuntimeError("Bot user is unavailable for setup sticky smoke.")

    await sync_subscription_setup(
        bot,
        context,
        guild,
        client=client,
        subscription=subscription,
        network=network,
        setup_mode="create",
    )

    refreshed = await context.client_repo.get_subscription_by_id(subscription.id)
    if refreshed is not None:
        subscription = refreshed

    expected_channel_name = f"🌐-{network.display_name}"
    subscribe_channel = guild.get_channel(subscription.subscribe_channel_id)
    publish_channel = guild.get_channel(subscription.publish_channel_id)

    if subscribe_channel is None:
        raise RuntimeError("Subscribe channel missing during setup sticky smoke.")

    subscribe_stickies = await _bot_messages_with_footer(
        subscribe_channel,
        bot_user_id=bot_user_id,
        footer_marker=_SUBSCRIBE_SETUP_FOOTER,
    )
    if not subscribe_stickies:
        raise RuntimeError("Subscribe setup sticky was not posted.")
    subscribe_text = _embed_blob(subscribe_stickies[0])
    if expected_channel_name not in subscribe_text:
        raise RuntimeError(
            "Subscribe setup sticky missing uniform channel name "
            f"{expected_channel_name!r}."
        )

    if publish_channel is None:
        raise RuntimeError("Publish channel missing during setup sticky smoke.")

    publish_stickies = await _bot_messages_with_footer(
        publish_channel,
        bot_user_id=bot_user_id,
        footer_marker=_PUBLISH_SETUP_FOOTER,
    )
    if not publish_stickies:
        raise RuntimeError("Publish setup sticky was not posted.")
    publish_text = _embed_blob(publish_stickies[0])
    if _DESKTOP_NOTE not in publish_text:
        raise RuntimeError("Publish setup sticky missing Discord desktop follow note.")


async def _trigger_activation_welcome(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    *,
    client: Client,
    subscription: ClientSubscription,
    network: Network,
) -> ClientSubscription:
    subscribe_channel = guild.get_channel(subscription.subscribe_channel_id)
    if subscribe_channel is None:
        raise RuntimeError("Subscribe channel missing for activation welcome smoke.")

    active_state = SubscriptionSetupState(
        publish_configured=True,
        subscribe_confirmed=True,
        network_active=True,
    )
    return await _maybe_post_activation_welcome(
        bot,
        subscription,
        subscribe_channel=subscribe_channel,
        context=context,
        guild=guild,
        network=network,
        client=client,
        setup_state=active_state,
    )


async def _assert_welcome_counts(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    *,
    joiner_subscription: ClientSubscription,
    incumbent_subscription: ClientSubscription,
    expected_incumbent_member_welcomes: int,
) -> None:
    bot_user_id = bot.user.id if bot.user is not None else 0
    joiner_channel = guild.get_channel(joiner_subscription.subscribe_channel_id)
    incumbent_channel = guild.get_channel(incumbent_subscription.subscribe_channel_id)
    if joiner_channel is None or incumbent_channel is None:
        raise RuntimeError("Subscribe channels missing during welcome count smoke.")

    joiner_activation = await _bot_messages_with_footer(
        joiner_channel,
        bot_user_id=bot_user_id,
        footer_marker=_ACTIVATION_FOOTER,
    )
    joiner_member = await _bot_messages_with_footer(
        joiner_channel,
        bot_user_id=bot_user_id,
        footer_marker=_MEMBER_FOOTER,
    )
    incumbent_member = await _bot_messages_with_footer(
        incumbent_channel,
        bot_user_id=bot_user_id,
        footer_marker=_MEMBER_FOOTER,
    )

    if len(joiner_activation) != 1:
        raise RuntimeError(
            "Joiner subscribe channel expected exactly one activation welcome "
            f"(found {len(joiner_activation)})."
        )
    if joiner_member:
        raise RuntimeError(
            "Joiner subscribe channel must not receive the network member broadcast welcome."
        )
    if len(incumbent_member) != expected_incumbent_member_welcomes:
        raise RuntimeError(
            "Incumbent subscribe channel expected "
            f"{expected_incumbent_member_welcomes} member welcome(s) "
            f"(found {len(incumbent_member)})."
        )


async def cleanup_smoke_welcome_clients(
    guild: discord.Guild,
    context: BotContext,
    bot_member: discord.Member,
) -> None:
    for client in await context.client_repo.list_all():
        if client.guild_id != guild.id:
            continue
        if not client.server_name.startswith(_SMOKE_WELCOME_PREFIX):
            continue
        await cleanup_smoke_client(
            guild,
            context,
            server_name=client.server_name,
            bot_member=bot_member,
        )


async def run_setup_welcome_smoke_flow(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
) -> SetupWelcomeSmokeResult:
    """Verify setup sticky copy, single joiner welcome, blacklist suppression, then broadcast."""
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")

    network_key = await ensure_smoke_network_key(context, bot, guild)
    network = await context.network_repo.get_by_key(network_key)
    if network is None:
        raise RuntimeError(f"Smoke network {network_key!r} was not found.")

    async with guild_test_resource_guard(guild, bot_member=bot_member):
        await cleanup_smoke_welcome_clients(guild, context, bot_member)
        incumbent_client: Client | None = None
        joiner_client: Client | None = None
        incumbent_server_name = ""
        joiner_server_name = ""

        try:
            incumbent_client, incumbent_sub = await _provision_smoke_welcome_client(
                guild,
                bot,
                context,
                network=network,
            )
            incumbent_server_name = incumbent_client.server_name

            joiner_client, joiner_sub = await _provision_smoke_welcome_client(
                guild,
                bot,
                context,
                network=network,
            )
            joiner_server_name = joiner_client.server_name

            await verify_setup_sticky_copy(
                guild,
                bot,
                context,
                client=joiner_client,
                subscription=joiner_sub,
                network=network,
            )

            await context.client_repo.add_blacklist(
                incumbent_sub.id,
                joiner_client.id,
            )
            joiner_sub = await _trigger_activation_welcome(
                bot,
                context,
                guild,
                client=joiner_client,
                subscription=joiner_sub,
                network=network,
            )
            await _assert_welcome_counts(
                guild,
                bot,
                joiner_subscription=joiner_sub,
                incumbent_subscription=incumbent_sub,
                expected_incumbent_member_welcomes=0,
            )

            await context.client_repo.remove_blacklist(
                incumbent_sub.id,
                joiner_client.id,
            )
            joiner_channel = guild.get_channel(joiner_sub.subscribe_channel_id)
            if joiner_channel is not None:
                for message in await _bot_messages_with_footer(
                    joiner_channel,
                    bot_user_id=bot.user.id if bot.user else 0,
                    footer_marker=_ACTIVATION_FOOTER,
                ):
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass

            joiner_sub = await context.client_repo.update_activation_welcome_message_id(
                joiner_sub.id,
                None,
            )
            joiner_sub = await _trigger_activation_welcome(
                bot,
                context,
                guild,
                client=joiner_client,
                subscription=joiner_sub,
                network=network,
            )
            await _assert_welcome_counts(
                guild,
                bot,
                joiner_subscription=joiner_sub,
                incumbent_subscription=incumbent_sub,
                expected_incumbent_member_welcomes=1,
            )

            return SetupWelcomeSmokeResult(
                incumbent_server_name=incumbent_server_name,
                joiner_server_name=joiner_server_name,
                network_key=network.key,
            )
        finally:
            if joiner_server_name:
                await cleanup_smoke_client(
                    guild,
                    context,
                    server_name=joiner_server_name,
                    bot_member=bot_member,
                )
            if incumbent_server_name:
                await cleanup_smoke_client(
                    guild,
                    context,
                    server_name=incumbent_server_name,
                    bot_member=bot_member,
                )
            await cleanup_smoke_welcome_clients(guild, context, bot_member)
