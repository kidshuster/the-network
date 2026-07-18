from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

import discord
from discord.abc import Messageable

from bot.constants import RelayStatus
from bot.db.repositories import RelayRecordRepository
from bot.domain.errors import RelayError
from bot.domain.relay_record import RelayResult
from bot.services.message_formatter import build_relay_payload, has_relayable_content
from bot.services.profile_cache import ProfileCache
from bot.services.routing_service import RoutingService

if TYPE_CHECKING:
    from bot.config import Settings

logger = logging.getLogger(__name__)

MAX_PUBLISH_RETRIES = 3


class RelayService:
    """Filter, transform, send, and publish followed announcement messages."""

    def __init__(
        self,
        settings: Settings,
        routing_service: RoutingService,
        profile_cache: ProfileCache,
        relay_record_repo: RelayRecordRepository,
    ) -> None:
        self._settings = settings
        self._routing = routing_service
        self._profiles = profile_cache
        self._relay_records = relay_record_repo
        self._locks: dict[int, asyncio.Lock] = {}

    def is_potential_feed_message(self, message: discord.Message) -> bool:
        if message.guild is None or message.guild.id != self._settings.guild_id:
            return False
        if message.author.bot and message.webhook_id is None:
            return False
        if self._routing.is_concat_channel(message.channel.id):
            return False
        return self._profiles.get_by_source_channel(message.channel.id) is not None

    def feed_reject_reason(self, message: discord.Message) -> str | None:
        """Explain why a message in a registered feed channel was not relayed."""
        if message.guild is None or message.guild.id != self._settings.guild_id:
            return None
        if self._profiles.get_by_source_channel(message.channel.id) is None:
            return None
        return self._filter_reject_reason(message)

    @staticmethod
    def _is_followed_message(message: discord.Message) -> bool:
        return message.webhook_id is not None

    def _filter_reject_reason(self, message: discord.Message) -> str | None:
        profile = self._profiles.get_enabled_by_source_channel(message.channel.id)
        if profile is None:
            disabled = self._profiles.get_by_source_channel(message.channel.id)
            if disabled is not None and not disabled.enabled:
                return "server profile is disabled"
            return "server profile not found"

        network = self._routing.get_by_id(profile.network_id)
        if network is None:
            return "network not found"
        if not network.enabled:
            return f"network '{network.key}' is disabled"

        if message.author.bot and not self._is_followed_message(message):
            return "message author is a bot (not a Channel Follow webhook)"

        if self._routing.is_concat_channel(message.channel.id):
            return "message is in the concat channel"

        if not self._is_followed_message(message) and not self._settings.manual_relay_enabled:
            return (
                "message is not from Channel Follow (no webhook_id); "
                "publish in the source server's announcement channel instead of posting here"
            )

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
        profile = self._profiles.get_enabled_by_source_channel(message.channel.id)
        if profile is None:
            return None

        network = self._routing.get_by_id(profile.network_id)
        if network is None or not network.enabled:
            return None

        if message.guild is None:
            return None

        output_channel = message.guild.get_channel(network.output_channel_id)
        if output_channel is None:
            logger.warning(
                "Output channel missing or invalid",
                extra={
                    "network_key": network.key,
                    "output_channel_id": network.output_channel_id,
                },
            )
            return None

        payload = await build_relay_payload(message, profile)

        try:
            record = await self._relay_records.create_pending(
                source_message_id=message.id,
                source_channel_id=message.channel.id,
                source_webhook_id=message.webhook_id,
                profile_id=profile.id,
                network_id=network.id,
                destination_channel_id=network.output_channel_id,
            )
        except RelayError:
            logger.debug(
                "Relay record race lost",
                extra={"source_message_id": message.id},
            )
            return None

        try:
            send_kwargs: dict[str, object] = {
                "embed": payload.embed,
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            if payload.files:
                send_kwargs["files"] = list(payload.files)
            sent = await cast(Messageable, output_channel).send(**send_kwargs)
        except discord.HTTPException as exc:
            await self._relay_records.update_status(
                record.id,
                status=RelayStatus.FAILED_SEND,
                error_message=str(exc),
            )
            logger.warning(
                "Relay send failed",
                extra={
                    "source_message_id": message.id,
                    "error": str(exc),
                },
            )
            return RelayResult(
                source_message_id=message.id,
                destination_message_ids=(),
                published_message_ids=(),
                success=False,
                error=str(exc),
            )

        await self._relay_records.update_status(
            record.id,
            status=RelayStatus.SENT,
            destination_message_ids=(sent.id,),
        )

        publish_error = await self._publish_with_retries(sent)
        if publish_error is not None:
            await self._relay_records.update_status(
                record.id,
                status=RelayStatus.FAILED_PUBLISH,
                destination_message_ids=(sent.id,),
                error_message=publish_error,
            )
            logger.warning(
                "Relay publish failed",
                extra={
                    "source_message_id": message.id,
                    "destination_message_id": sent.id,
                    "error": publish_error,
                },
            )
            return RelayResult(
                source_message_id=message.id,
                destination_message_ids=(sent.id,),
                published_message_ids=(),
                success=False,
                error=publish_error,
            )

        await self._relay_records.update_status(
            record.id,
            status=RelayStatus.PUBLISHED,
            destination_message_ids=(sent.id,),
        )
        logger.info(
            "Relay published",
            extra={
                "source_message_id": message.id,
                "destination_message_id": sent.id,
                "network_key": network.key,
                "profile": profile.server_name,
            },
        )
        return RelayResult(
            source_message_id=message.id,
            destination_message_ids=(sent.id,),
            published_message_ids=(sent.id,),
            success=True,
            error=None,
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

    @staticmethod
    def _is_transient(exc: discord.HTTPException) -> bool:
        if exc.status in {429, 500, 502, 503, 504}:
            return True
        return exc.code in {50035}
