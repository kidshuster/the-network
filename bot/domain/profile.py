from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServerProfile:
    id: int
    guild_id: int
    profile_thread_id: int
    profile_starter_message_id: int
    source_channel_id: int
    network_id: int
    server_name: str
    display_name: str
    enabled: bool
    emoji_id: int | None
    emoji_name: str | None
    image_hash: str | None
    degraded_reason: str | None
    partner_role_id: int | None
    profile_forum_channel_id: int | None
