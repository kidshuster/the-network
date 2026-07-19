from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ServerRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


@dataclass(frozen=True)
class ServerRequest:
    id: int
    guild_id: int
    network_id: int
    requester_user_id: int
    server_name: str
    display_name: str
    profile_image_url: str
    profile_image_data: bytes | None
    status: ServerRequestStatus
    moderator_message_id: int | None
    resolved_by_user_id: int | None
    created_at: str
    updated_at: str
