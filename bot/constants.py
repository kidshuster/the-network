from __future__ import annotations

from enum import StrEnum


class RelayStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    PUBLISHED = "published"
    FAILED_SEND = "failed_send"
    FAILED_PUBLISH = "failed_publish"
    PARTIAL = "partial"


DEGRADED_FALLBACK = "◈"

SCHEMA_VERSION = 7

DEFAULT_NETWORK_ACCESS_ROLE_NAME = "The Network"
DEFAULT_NETWORK_MODERATOR_ROLE_NAME = "The Network Moderator"
LEGACY_MODERATOR_ROLE_NAME = "Moderator"

SETTING_PROFILE_FORUM_CHANNEL_ID = "profile_forum_channel_id"

MAX_PROFILE_IMAGE_DOWNLOAD_BYTES = 8 * 1024 * 1024
MAX_EMOJI_FILE_BYTES = 256 * 1024
EMOJI_SIZE = 128
