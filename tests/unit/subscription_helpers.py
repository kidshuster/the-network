from __future__ import annotations

from bot.core.models.client_subscription import ClientSubscription


def make_client_subscription(**overrides: object) -> ClientSubscription:
    defaults: dict[str, object] = {
        "id": 1,
        "client_id": 1,
        "network_id": 2,
        "network_key": "stingers",
        "publish_channel_id": 100,
        "subscribe_channel_id": 101,
        "announcements_channel_id": None,
        "moderation_message_id": None,
        "publish_setup_message_id": None,
        "subscribe_setup_message_id": None,
        "announcements_sticky_message_id": None,
        "activation_welcome_message_id": None,
        "network_welcome_message_id": None,
        "network_welcome_complete": False,
        "subscribe_confirmed": False,
        "enabled": True,
    }
    defaults.update(overrides)
    return ClientSubscription(**defaults)  # type: ignore[arg-type]
