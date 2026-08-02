from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Client:
    id: int
    guild_id: int
    server_name: str
    display_name: str
    category_id: int
    client_role_id: int
    profile_channel_id: int
    profile_message_id: int
    enabled: bool
    emoji_id: int | None
    emoji_name: str | None
    image_hash: str | None
    degraded_reason: str | None
