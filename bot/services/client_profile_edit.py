from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.domain.client import Client
from bot.domain.errors import ProfileValidationError
from bot.services.client_profile_sync import refresh_client_profile_message
from bot.services.image_service import normalize_image_bytes, read_profile_image_attachment
from bot.services.view_registry import ViewRegistry

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClientProfileUpdateResult:
    success: bool
    client: Client | None = None
    error: str | None = None
    warnings: tuple[str, ...] = ()


async def apply_client_profile_edit(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
    *,
    client_id: int,
    display_name: str,
    profile_image: discord.Attachment | None = None,
    view_registry: ViewRegistry,
) -> ClientProfileUpdateResult:
    client = await context.client_repo.get_by_id(client_id)
    if client is None:
        return ClientProfileUpdateResult(success=False, error="Client profile was not found.")

    label = display_name.strip()
    if not label:
        return ClientProfileUpdateResult(success=False, error="Display name cannot be empty.")

    warnings: list[str] = []
    updated = await context.client_repo.update_display_name(client_id, label)

    if profile_image is not None:
        try:
            raw = await read_profile_image_attachment(profile_image)
            normalized = normalize_image_bytes(raw.data)
        except ProfileValidationError as exc:
            return ClientProfileUpdateResult(success=False, error=str(exc))

        from bot.services.emoji_service import EmojiService, emoji_sync_target_from_client

        emoji_service = EmojiService()
        emoji_result = await emoji_service.sync_for_profile(
            guild,
            emoji_sync_target_from_client(updated),
            normalized,
            previous_hash=updated.image_hash,
            previous_emoji_id=updated.emoji_id,
            force=True,
        )
        if emoji_result.warning:
            warnings.append(emoji_result.warning)
        updated = await context.client_repo.update_emoji_fields(
            client_id,
            emoji_id=emoji_result.emoji_id,
            emoji_name=emoji_result.emoji_name,
            image_hash=emoji_result.image_hash,
            degraded_reason=emoji_result.degraded_reason,
        )
        if emoji_result.delete_emoji_id is not None:
            await emoji_service.delete_emoji(guild, emoji_result.delete_emoji_id)

    await refresh_client_profile_message(
        bot,
        context,
        guild,
        updated,
        view_registry=view_registry,
    )
    return ClientProfileUpdateResult(
        success=True,
        client=updated,
        warnings=tuple(warnings),
    )
