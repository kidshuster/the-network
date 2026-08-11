from __future__ import annotations

from bot.core.models.server_request import ServerRequest, ServerRequestStatus


def make_server_request(**overrides: object) -> ServerRequest:
    defaults: dict[str, object] = {
        "id": 7,
        "guild_id": 100,
        "network_id": None,
        "requester_user_id": 555,
        "server_name": "Acme",
        "display_name": "Acme",
        "profile_image_url": "https://cdn.example/profile.png",
        "profile_image_data": b"png",
        "status": ServerRequestStatus.PENDING,
        "moderator_message_id": 900,
        "resolved_by_user_id": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return ServerRequest(**defaults)  # type: ignore[arg-type]
