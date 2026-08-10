from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord

from bot.clients.profile_post import build_client_profile_embed
from bot.clients.profile_sync import refresh_client_profile_message
from bot.clients.provision import ClientProvisionService
from bot.config import Settings
from bot.domain.client import Client
from bot.domain.network import Network
from bot.hub.resolve import (
    find_network_announcements_text_channel,
    resolve_moderation_category,
    resolve_network_announcements_channel,
)
from bot.media.emoji import EmojiService, emoji_sync_target_from_client
from bot.media.image import download_profile_image_from_url, normalize_image_bytes
from bot.messages import render_embed
from bot.networks.roles import resolve_operator_role_by_name
from bot.ui.view_registry import ViewRegistry

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext
    from bot.domain.client_subscription import ClientSubscription
    from bot.hub.result import GuildInitResult

logger = logging.getLogger(__name__)

_GUIDE_FOOTER = "hub announcements guide"
_INJECT_WEBHOOK_NAME = "network-hub-inject"
_SINGLE_LINE_PREFIX_RE = re.compile(r"^\[([a-z0-9_-]+)\]$", re.IGNORECASE)


def is_hub_announcements_client(client: Client, settings: Settings) -> bool:
    return (
        client.server_name.casefold()
        == settings.hub_announcements_server_name.casefold()
    )


@dataclass(frozen=True)
class ParsedAnnouncement:
    network_keys: tuple[str, ...]
    body: str
    error: str | None = None


def parse_announcement_content(
    content: str,
    *,
    available_keys: set[str],
) -> ParsedAnnouncement:
    text = content or ""
    lines = text.splitlines()
    if lines:
        first_line = lines[0].strip()
        match = _SINGLE_LINE_PREFIX_RE.match(first_line)
        if match is not None:
            key = match.group(1).casefold()
            body = "\n".join(lines[1:]).strip()
            if key not in available_keys:
                keys_list = ", ".join(f"`{k}`" for k in sorted(available_keys))
                return ParsedAnnouncement(
                    (),
                    body,
                    f"Unknown network `{key}`. Available: {keys_list or '(none)'}.",
                )
            if not body:
                return ParsedAnnouncement(
                    (),
                    body,
                    "Message body is empty after the network prefix.",
                )
            return ParsedAnnouncement((key,), body)

    body = text.strip()
    return ParsedAnnouncement(tuple(sorted(available_keys)), body)


def can_post_hub_announcement(
    member: discord.Member,
    guild: discord.Guild,
    settings: Settings,
) -> bool:
    from bot.hub.resolve import resolve_human_moderator_role

    operator = resolve_operator_role_by_name(
        guild,
        role_name=settings.network_operator_role_name,
    )
    if operator is not None and operator in member.roles:
        return True
    moderator = resolve_human_moderator_role(guild)
    if moderator is not None and moderator in member.roles:
        return True
    return member.guild_permissions.manage_guild


async def _ensure_mod_announcements_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    human_moderator_role: discord.Role | None,
    settings: Settings,
    *,
    result: GuildInitResult | None = None,
) -> discord.TextChannel | None:
    from bot.layout import ApplyMode, LayoutContext, apply_layout, compile_hub_slice

    moderation = resolve_moderation_category(guild)
    if moderation is None:
        return None

    operator = resolve_operator_role_by_name(
        guild,
        role_name=settings.network_operator_role_name,
    )
    layout_ctx = LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=None,
        moderator_role=human_moderator_role,
        operator_role=operator,
        reason="The Network hub announcements",
    )
    batch = await apply_layout(
        layout_ctx,
        compile_hub_slice(
            layout_ctx,
            category_ids={"moderation"},
            channel_ids={"network_announcements"},
        ),
        mode=ApplyMode.ENSURE,
    )
    channel = batch.resource("network_announcements")
    if isinstance(channel, discord.TextChannel):
        await _sync_guide_sticky(channel, bot_member)
        return channel

    if result is not None:
        if batch.failures:
            result.failed_steps.extend(
                f"layout network_announcements: {detail}" for detail in batch.failures
            )
        legacy = find_network_announcements_text_channel(
            guild,
            category_id=moderation.id,
            include_announcement=False,
        )
        if legacy is not None:
            result.rectification_failures.append(
                f"{legacy.mention} is a plain text channel — could not convert to "
                "announcement type (check bot **Manage Channels**)."
            )
    return None


async def _sync_guide_sticky(
    channel: discord.TextChannel,
    bot_member: discord.Member,
) -> None:
    embed = render_embed("hub_announcements_guide")
    marker = _GUIDE_FOOTER.casefold()
    try:
        async for message in channel.history(limit=20):
            if message.author.id != bot_member.id or not message.embeds:
                continue
            footer = (message.embeds[0].footer.text or "").casefold()
            if marker in footer:
                try:
                    await message.edit(embed=embed)
                except discord.HTTPException:
                    pass
                return
    except discord.HTTPException:
        pass
    try:
        await channel.send(embed=embed, silent=True)
    except discord.HTTPException:
        logger.warning(
            "Could not post hub announcements guide",
            extra={"channel_id": channel.id},
        )


async def _download_bot_avatar_image(bot: NetworkRelayBot) -> bytes | None:
    user = bot.user
    if user is None:
        return None
    url = str(user.display_avatar.url)
    try:
        image = await download_profile_image_from_url(url)
        return image.data
    except Exception:
        logger.warning("Could not download bot avatar for hub announcements client")
        return None


async def _sync_hub_client_emoji(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    client: Client,
    *,
    image_data: bytes | None,
) -> Client:
    if image_data is None:
        return client
    image = normalize_image_bytes(image_data)
    emoji_service = EmojiService()
    emoji_result = await emoji_service.sync_for_profile(
        guild,
        emoji_sync_target_from_client(client),
        image,
        previous_hash=client.image_hash,
        previous_emoji_id=client.emoji_id,
        force=True,
    )
    if emoji_result.emoji_id is None:
        return client
    return await context.client_repo.update_emoji_fields(
        client.id,
        emoji_id=emoji_result.emoji_id,
        emoji_name=emoji_result.emoji_name,
        image_hash=emoji_result.image_hash,
        degraded_reason=emoji_result.degraded_reason,
    )


async def _create_hub_client_record(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    bot_member: discord.Member,
    *,
    view_registry: ViewRegistry,
) -> Client:
    settings = bot.settings
    provision_service = ClientProvisionService()
    provision = await provision_service.provision_client(
        guild,
        bot_member,
        server_name=settings.hub_announcements_server_name,
        access_role_name=settings.network_access_role_name,
        operator_role_name=settings.network_operator_role_name,
    )

    networks = await context.network_repo.list_all()
    network_keys = [n.key for n in networks]
    view = view_registry.register_client_profile_view(0, network_keys)
    embed = build_client_profile_embed(
        server_name=settings.hub_announcements_server_name,
        display_name=settings.hub_announcements_display_name,
        enabled=True,
    )
    starter = await provision.profile_channel.send(embed=embed, view=view, silent=True)

    client = await context.client_repo.create(
        guild_id=guild.id,
        server_name=settings.hub_announcements_server_name,
        display_name=settings.hub_announcements_display_name,
        category_id=provision.category.id,
        client_role_id=provision.client_role.id,
        profile_channel_id=provision.profile_channel.id,
        profile_message_id=starter.id,
    )

    view = view_registry.register_client_profile_for_client(client, network_keys)
    await starter.edit(view=view)

    avatar = await _download_bot_avatar_image(bot)
    client = await _sync_hub_client_emoji(guild, bot, context, client, image_data=avatar)
    await refresh_client_profile_message(
        bot,
        context,
        guild,
        client,
        view_registry=view_registry,
    )
    return client


async def _finalize_hub_subscription(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    subscription_id: int,
) -> None:
    subscription = await context.client_repo.set_subscribe_confirmed(subscription_id, True)
    if subscription.publish_setup_message_id is not None:
        publish = guild.get_channel(subscription.publish_channel_id)
        if isinstance(publish, discord.TextChannel):
            try:
                message = await publish.fetch_message(subscription.publish_setup_message_id)
                await message.delete()
            except discord.HTTPException:
                pass
        subscription = await context.client_repo.update_publish_setup_message_id(
            subscription.id,
            None,
        )
    if subscription.subscribe_setup_message_id is not None:
        subscribe = guild.get_channel(subscription.subscribe_channel_id)
        if subscribe is not None and hasattr(subscribe, "fetch_message"):
            try:
                message = await subscribe.fetch_message(subscription.subscribe_setup_message_id)
                await message.delete()
            except discord.HTTPException:
                pass
        await context.client_repo.update_subscribe_setup_message_id(subscription.id, None)


async def ensure_hub_announcements_subscription(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    network: Network,
) -> bool:
    """Subscribe the hub announcements client to one network if missing."""
    settings = bot.settings
    client = await context.client_repo.get_by_server_name(
        guild.id,
        settings.hub_announcements_server_name,
    )
    if client is None:
        return False

    existing = await context.client_repo.get_subscription(client.id, network.id)
    if existing is not None:
        await _finalize_hub_subscription(bot, context, guild, existing.id)
        return False

    bot_member = guild.me
    if bot_member is None:
        return False

    from bot.clients.subscription import ClientSubscriptionService

    sub_service = ClientSubscriptionService()
    result = await sub_service.subscribe_client(
        guild,
        bot_member,
        client=client,
        network_id=network.id,
        network_key=network.key,
        client_repo=context.client_repo,
        network_repo=context.network_repo,
        access_role_name=settings.network_access_role_name,
    )
    if not result.success or result.subscription is None:
        logger.warning(
            "Hub announcements subscribe failed",
            extra={"network_key": network.key, "error": result.error},
        )
        return False

    await _finalize_hub_subscription(bot, context, guild, result.subscription.id)
    await context.client_cache.load_cache()
    await context.routing_service.load_cache()
    return True


async def ensure_hub_announcements_client(
    guild: discord.Guild,
    bot: NetworkRelayBot,
    context: BotContext,
    *,
    result: GuildInitResult | None = None,
    view_registry: ViewRegistry,
) -> Client | None:
    """Ensure hub announcements client, mod channel, and all network subscriptions."""
    if guild.id != bot.settings.guild_id:
        return None

    bot_member = guild.me
    if bot_member is None:
        return None

    from bot.hub.resolve import resolve_human_moderator_role

    settings = bot.settings
    human_moderator_role = resolve_human_moderator_role(guild)
    await _ensure_mod_announcements_channel(
        guild,
        bot_member,
        human_moderator_role,
        settings,
        result=result,
    )

    client = await context.client_repo.get_by_server_name(
        guild.id,
        settings.hub_announcements_server_name,
    )
    if client is None:
        try:
            client = await _create_hub_client_record(
                guild,
                bot,
                context,
                bot_member,
                view_registry=view_registry,
            )
            if result is not None:
                result.notes.append(
                    "Created hub announcements client "
                    f"**{settings.hub_announcements_display_name}**."
                )
        except Exception as exc:
            logger.exception("Failed to create hub announcements client")
            if result is not None:
                result.rectification_failures.append(
                    f"Hub announcements client: {type(exc).__name__}: {exc}"
                )
            return None
    else:
        avatar = await _download_bot_avatar_image(bot)
        client = await _sync_hub_client_emoji(
            guild,
            bot,
            context,
            client,
            image_data=avatar,
        )
        if client.display_name != settings.hub_announcements_display_name:
            client = await context.client_repo.update_display_name(
                client.id,
                settings.hub_announcements_display_name,
            )

    networks = await context.network_repo.list_all()
    subscribed = 0
    for network in networks:
        if not network.enabled:
            continue
        if await ensure_hub_announcements_subscription(guild, bot, context, network):
            subscribed += 1
        else:
            existing = await context.client_repo.get_subscription(client.id, network.id)
            if existing is not None:
                await _finalize_hub_subscription(bot, context, guild, existing.id)

    if subscribed and result is not None:
        result.notes.append(
            f"Hub announcements client subscribed to {subscribed} network(s)."
        )

    await context.refresh_client_counts()
    return client


async def _get_or_create_inject_webhook(
    channel: discord.TextChannel,
) -> discord.Webhook:
    try:
        for webhook in await channel.webhooks():
            if webhook.name == _INJECT_WEBHOOK_NAME:
                return webhook
    except discord.HTTPException as exc:
        raise RuntimeError(f"Could not list webhooks: {exc}") from exc
    try:
        return await channel.create_webhook(
            name=_INJECT_WEBHOOK_NAME,
            reason="The Network hub announcements inject",
        )
    except discord.HTTPException as exc:
        raise RuntimeError(f"Could not create inject webhook: {exc}") from exc


async def _build_webhook_files(
    message: discord.Message,
) -> list[discord.File] | None:
    if not message.attachments:
        return None
    files: list[discord.File] = []
    for attachment in message.attachments:
        try:
            data = await attachment.read()
        except discord.HTTPException:
            continue
        files.append(discord.File(io.BytesIO(data), filename=attachment.filename))
    return files or None


async def inject_hub_announcement(
    publish_channel: discord.TextChannel,
    *,
    content: str,
    embeds: list[discord.Embed] | None = None,
    files: list[discord.File] | None = None,
) -> discord.Message:
    webhook = await _get_or_create_inject_webhook(publish_channel)
    try:
        kwargs: dict[str, Any] = {
            "content": content or None,
            "wait": True,
            "silent": True,
        }
        if embeds:
            kwargs["embeds"] = embeds
        if files:
            kwargs["files"] = files
        message = await webhook.send(**kwargs)
        assert isinstance(message, discord.Message)
        return message
    except discord.HTTPException as exc:
        raise RuntimeError(f"Webhook inject failed: {exc}") from exc


@dataclass(frozen=True)
class DispatchResult:
    success: bool
    networks_attempted: tuple[str, ...]
    networks_relayed: tuple[str, ...]
    errors: tuple[str, ...]


async def dispatch_hub_announcement(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    message: discord.Message,
) -> DispatchResult:
    settings = bot.settings
    client = await context.client_repo.get_by_server_name(
        guild.id,
        settings.hub_announcements_server_name,
    )
    if client is None:
        return DispatchResult(False, (), (), ("Hub announcements client is not configured.",))

    subscriptions = await context.client_repo.list_subscriptions_by_client(client.id)
    key_to_sub: dict[str, ClientSubscription] = {}
    for sub in subscriptions:
        if not sub.enabled or sub.network_id is None:
            continue
        network = await context.network_repo.get_by_id(sub.network_id)
        if network is None or not network.enabled:
            continue
        key_to_sub[network.key] = sub

    available = set(key_to_sub)
    parsed = parse_announcement_content(message.content or "", available_keys=available)
    if parsed.error is not None:
        return DispatchResult(False, (), (), (parsed.error,))

    if (
        not parsed.body
        and not message.embeds
        and not message.attachments
    ):
        return DispatchResult(False, (), (), ("Message is empty.",))

    targets = [k for k in parsed.network_keys if k in key_to_sub]
    if not targets:
        return DispatchResult(False, (), (), ("No enabled network subscriptions found.",))

    embeds = list(message.embeds) if message.embeds else None
    attachment_files = await _build_webhook_files(message)

    relayed: list[str] = []
    errors: list[str] = []

    for key in targets:
        sub = key_to_sub[key]
        publish = guild.get_channel(sub.publish_channel_id)
        if not isinstance(publish, discord.TextChannel):
            errors.append(f"`{key}`: publish channel missing")
            continue
        try:
            sent = await inject_hub_announcement(
                publish,
                content=parsed.body,
                embeds=embeds,
                files=attachment_files,
            )
            result = await context.relay_service.relay_message(sent)
            if result is None or not result.success:
                reason = context.relay_service.feed_reject_reason(sent) or "relay failed"
                errors.append(f"`{key}`: {reason}")
                continue
            relayed.append(key)
        except RuntimeError as exc:
            errors.append(f"`{key}`: {exc}")

    return DispatchResult(
        success=bool(relayed) and not errors,
        networks_attempted=tuple(targets),
        networks_relayed=tuple(relayed),
        errors=tuple(errors),
    )


async def handle_network_announcements_message(
    bot: NetworkRelayBot,
    message: discord.Message,
) -> None:
    context = bot.bot_context
    if context is None or message.guild is None:
        return
    if message.author.bot:
        return

    announcements = resolve_network_announcements_channel(message.guild)
    if announcements is None or message.channel.id != announcements.id:
        return

    member = message.author
    if not isinstance(member, discord.Member):
        return
    if not can_post_hub_announcement(member, message.guild, bot.settings):
        return

    result = await dispatch_hub_announcement(bot, context, message.guild, message)
    if result.networks_relayed:
        networks_label = ", ".join(f"`{k}`" for k in result.networks_relayed)
        reply = f"Relayed to {networks_label}."
        if result.errors:
            reply += " " + " ".join(result.errors)
        colour = "green" if not result.errors else "yellow"
    else:
        reply = result.errors[0] if result.errors else "Announcement was not relayed."
        colour = "red"

    try:
        await message.reply(
            embed=render_embed(
                "review_success",
                label="Announcements",
                colour=colour,
                description=reply,
            ),
            mention_author=False,
        )
    except discord.HTTPException:
        pass
