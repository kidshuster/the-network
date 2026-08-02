from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClientSubscription:
    id: int
    client_id: int
    network_id: int | None
    network_key: str
    publish_channel_id: int
    subscribe_channel_id: int
    moderation_message_id: int | None
    enabled: bool
