from __future__ import annotations

from dataclasses import dataclass

from bot.constants import RelayStatus


@dataclass(frozen=True)
class RelayRecord:
    id: int
    source_message_id: int
    source_channel_id: int
    source_webhook_id: int | None
    profile_id: int
    network_id: int
    destination_channel_id: int
    destination_message_ids: tuple[int, ...]
    status: RelayStatus
    error_message: str | None


@dataclass(frozen=True)
class RelayResult:
    source_message_id: int
    destination_message_ids: tuple[int, ...]
    published_message_ids: tuple[int, ...]
    success: bool
    error: str | None
