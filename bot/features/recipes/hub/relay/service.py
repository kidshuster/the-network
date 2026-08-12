from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

import discord
from discord.abc import Messageable

from bot.constants import RelayStatus
from bot.core.clients.cache import ClientCache
from bot.core.database.store import RelayStore
from bot.core.models.errors import RelayError
from bot.core.models.relay_record import RelayResult
from bot.core.networks.routing import RoutingService
from bot.features.recipes.hub.relay.formatter import (
    RelayPayload,
    build_relay_payload_from_client,
    build_system_announcement_payload,
)

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.core.database.store import ClientStore

logger = logging.getLogger(__name__)

MAX_PUBLISH_RETRIES = 3


class RelayService:
    """Filter, transform, send, and publish followed announcement messages."""

    def __init__(
        self,
        settings: Settings,
        routing_service: RoutingService,
        client_cache: ClientCache,
        client_repo: ClientStore,
        relay_record_repo: RelayStore,
    ) -> None:
        self._settings = settings
        self._routing = routing_service
        self._clients = client_cache
        self._client_repo = client_repo
        self._relay_records = relay_record_repo
        self._locks: dict[int, asyncio.Lock] = {}

    def is_potential_feed_message(self, message: discord.Message) -> bool:
        if message.guild is None or message.guild.id != self._settings.guild_id:
            return False
        if message.author.bot and message.webhook_id is None:
            return False
        return self._routing.resolve_publish_subscription(message.channel.id) is not None

    def feed_reject_reason(self, message: discord.Message) -> str | None:
        if message.guild is None or message.guild.id != self._settings.guild_id:
            return None
        if self._routing.resolve_publish_subscription(message.channel.id) is None:
            return None
        return self._filter_reject_reason(message)

    @staticmethod
    def _is_followed_message(message: discord.Message) -> bool:
        webhook_id = message.webhook_id
        return webhook_id is not None and webhook_id != 0

    def _filter_reject_reason(self, message: discord.Message) -> str | None:
        subscription = self._routing.resolve_publish_subscription(message.channel.id)
        if subscription is None:
            return "publish channel not registered"

        network = (
            self._routing.get_by_id(subscription.network_id)
            if subscription.network_id is not None
            else None
        )
        if network is None:
            return "network not found"
        if not network.enabled:
            return f"network '{network.key}' is disabled"

        client = self._clients.get_client(subscription.client_id)
        if client is None:
            return "client not found"
        if not client.enabled:
            return "client is disabled"

        if message.author.bot and not self._is_followed_message(message):
            return "message author is a bot (not a Channel Follow webhook)"

        if not self._is_followed_message(message) and not self._settings.manual_relay_enabled:
            return (
                "message is not from Channel Follow (no webhook_id); "
                "publish in the source server's announcement channel instead"
            )

        from bot.features.recipes.hub.relay.formatter import has_relayable_content

        if not has_relayable_content(message):
            return "message has no relayable text, embed, or attachment content"

        return None

    async def relay_message(self, message: discord.Message) -> RelayResult | None:
        if not self._passes_filters(message):
            return None

        lock = self._locks.setdefault(message.id, asyncio.Lock())
        async with lock:
            if await self._relay_records.exists(message.id):
                logger.debug(
                    "Skipping duplicate relay",
                    extra={"source_message_id": message.id},
                )
                return None
            return await self._relay_locked(message)

    def _passes_filters(self, message: discord.Message) -> bool:
        if message.guild is None or message.guild.id != self._settings.guild_id:
            return False
        return self._filter_reject_reason(message) is None

    async def _relay_locked(self, message: discord.Message) -> RelayResult | None:
        publisher_sub = self._routing.resolve_publish_subscription(message.channel.id)
        if publisher_sub is None:
            return None

        publisher = self._clients.get_client(publisher_sub.client_id)
        if publisher is None:
            return None

        network = (
            self._routing.get_by_id(publisher_sub.network_id)
            if publisher_sub.network_id is not None
            else None
        )
        if network is None or not network.enabled:
            return None

        if message.guild is None:
            return None

        payload = await build_relay_payload_from_client(message, publisher)

        destinations = self._routing.list_network_subscriptions(network.id)
        sent_ids: list[int] = []
        published_ids: list[int] = []
        first_dest_channel_id: int | None = None
        errors: list[str] = []

        try:
            record = await self._relay_records.create_pending(
                source_message_id=message.id,
                source_channel_id=message.channel.id,
                source_webhook_id=message.webhook_id,
                client_id=publisher.id,
                network_id=network.id,
                destination_channel_id=first_dest_channel_id or 0,
            )
        except RelayError:
            return None

        for dest_sub in destinations:
            if not dest_sub.enabled:
                continue
            subscriber = self._clients.get_client(dest_sub.client_id)
            if subscriber is None or not subscriber.enabled:
                continue
            if await self._client_repo.is_relay_blocked(
                publisher_subscription_id=publisher_sub.id,
                publisher_client_id=publisher.id,
                destination_subscription_id=dest_sub.id,
                destination_client_id=dest_sub.client_id,
            ):
                continue

            output_channel = message.guild.get_channel(dest_sub.subscribe_channel_id)
            if output_channel is None:
                errors.append(f"missing subscribe channel {dest_sub.subscribe_channel_id}")
                continue

            if first_dest_channel_id is None:
                first_dest_channel_id = dest_sub.subscribe_channel_id

            try:
                send_kwargs: dict[str, Any] = {
                    "embed": payload.embed,
                    "allowed_mentions": discord.AllowedMentions.none(),
                    "silent": True,
                }
                if payload.files:
                    send_kwargs["files"] = list(payload.files)
                sent = await cast(Messageable, output_channel).send(**send_kwargs)
                sent_ids.append(sent.id)
                publish_error = await self._publish_with_retries(sent)
                if publish_error is not None:
                    errors.append(publish_error)
                else:
                    published_ids.append(sent.id)
            except discord.HTTPException as exc:
                errors.append(str(exc))

        if not sent_ids:
            error_msg = errors[0] if errors else "no relay destinations"
            await self._relay_records.update_status(
                record.id,
                status=RelayStatus.FAILED_SEND,
                error_message=error_msg,
            )
            return RelayResult(
                source_message_id=message.id,
                destination_message_ids=(),
                published_message_ids=(),
                success=False,
                error=error_msg,
            )

        status = RelayStatus.PUBLISHED if published_ids else RelayStatus.FAILED_PUBLISH
        if published_ids and len(published_ids) < len(sent_ids):
            status = RelayStatus.PARTIAL

        await self._relay_records.update_status(
            record.id,
            status=status,
            destination_message_ids=tuple(sent_ids),
            error_message="; ".join(errors) if errors else None,
        )

        return RelayResult(
            source_message_id=message.id,
            destination_message_ids=tuple(sent_ids),
            published_message_ids=tuple(published_ids),
            success=bool(published_ids),
            error="; ".join(errors) if errors and not published_ids else None,
        )

    async def _publish_with_retries(self, message: discord.Message) -> str | None:
        last_error: str | None = None
        for attempt in range(1, MAX_PUBLISH_RETRIES + 1):
            try:
                await message.publish()
                return None
            except discord.HTTPException as exc:
                last_error = str(exc)
                if attempt < MAX_PUBLISH_RETRIES and self._is_transient(exc):
                    await asyncio.sleep(0.5 * attempt)
                    continue
                return last_error
        return last_error

    async def deliver_system_announcement(
        self,
        message: discord.Message,
        *,
        network_id: int,
        body: str,
        about_client_id: int | None = None,
        exclude_client_id: int | None = None,
        author_icon_url: str | None = None,
    ) -> RelayResult:
        """Deliver a trusted hub announcement without manufacturing a client.

        ``about_client_id`` honors per-subscription blacklists for that client.
        ``exclude_client_id`` skips the joining client's own subscribe channel.
        """
        payload = await build_system_announcement_payload(
            message,
            body=body,
            author_icon_url=author_icon_url,
        )
        destinations = self._routing.list_network_subscriptions(network_id)
        sent_ids: list[int] = []
        published_ids: list[int] = []
        errors: list[str] = []
        seen_channels: set[int] = set()
        for subscription in destinations:
            if not subscription.enabled or subscription.subscribe_channel_id in seen_channels:
                continue
            if exclude_client_id is not None and subscription.client_id == exclude_client_id:
                continue
            client = self._clients.get_client(subscription.client_id)
            if client is None or not client.enabled or message.guild is None:
                continue
            if about_client_id is not None and await self._client_repo.is_blacklisted(
                subscription.id,
                about_client_id,
            ):
                continue
            seen_channels.add(subscription.subscribe_channel_id)
            channel = message.guild.get_channel(subscription.subscribe_channel_id)
            if channel is None:
                errors.append(f"missing subscribe channel {subscription.subscribe_channel_id}")
                continue
            try:
                sent = await self._send_payload(channel, payload)
                sent_ids.append(sent.id)
                publish_error = await self._publish_with_retries(sent)
                if publish_error is None:
                    published_ids.append(sent.id)
                else:
                    errors.append(publish_error)
            except discord.HTTPException as exc:
                errors.append(str(exc))
        return RelayResult(
            source_message_id=message.id,
            destination_message_ids=tuple(sent_ids),
            published_message_ids=tuple(published_ids),
            success=not errors,
            error="; ".join(errors) if errors else None,
        )

    @staticmethod
    async def _send_payload(
        channel: object,
        payload: RelayPayload,
    ) -> discord.Message:
        kwargs: dict[str, Any] = {
            "embed": payload.embed,
            "allowed_mentions": discord.AllowedMentions.none(),
            "silent": True,
        }
        if payload.files:
            kwargs["files"] = list(payload.files)
        return await cast(Messageable, channel).send(**kwargs)

    @staticmethod
    def _is_transient(exc: discord.HTTPException) -> bool:
        if exc.status in {429, 500, 502, 503, 504}:
            return True
        return exc.code in {50035}
