from __future__ import annotations

import json
from typing import Any

from bot.constants import RelayStatus
from bot.domain.network import Network
from bot.domain.profile import ServerProfile
from bot.domain.relay_record import RelayRecord


class NetworkRow:
    @staticmethod
    def from_row(row: Any) -> Network:
        return Network(
            id=int(row["id"]),
            key=str(row["key"]),
            display_name=str(row["display_name"]),
            feed_category_id=int(row["feed_category_id"]),
            output_channel_id=int(row["output_channel_id"]),
            concat_channel_id=(
                int(row["concat_channel_id"]) if row["concat_channel_id"] is not None else None
            ),
            profile_forum_channel_id=(
                int(row["profile_forum_channel_id"])
                if "profile_forum_channel_id" in row.keys()
                and row["profile_forum_channel_id"] is not None
                else None
            ),
            enabled=bool(row["enabled"]),
        )


class ProfileRow:
    @staticmethod
    def from_row(row: Any) -> ServerProfile:
        return ServerProfile(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            profile_thread_id=int(row["profile_thread_id"]),
            profile_starter_message_id=int(row["profile_starter_message_id"]),
            source_channel_id=int(row["source_channel_id"]),
            network_id=int(row["network_id"]),
            server_name=str(row["server_name"]),
            display_name=str(row["display_name"]),
            enabled=bool(row["enabled"]),
            emoji_id=int(row["emoji_id"]) if row["emoji_id"] is not None else None,
            emoji_name=str(row["emoji_name"]) if row["emoji_name"] is not None else None,
            image_hash=str(row["image_hash"]) if row["image_hash"] is not None else None,
            degraded_reason=(
                str(row["degraded_reason"]) if row["degraded_reason"] is not None else None
            ),
            partner_role_id=(
                int(row["partner_role_id"])
                if "partner_role_id" in row.keys() and row["partner_role_id"] is not None
                else None
            ),
            profile_forum_channel_id=(
                int(row["profile_forum_channel_id"])
                if "profile_forum_channel_id" in row.keys()
                and row["profile_forum_channel_id"] is not None
                else None
            ),
        )


class RelayRecordRow:
    @staticmethod
    def from_row(row: Any) -> RelayRecord:
        raw_ids = row["destination_message_ids"]
        if isinstance(raw_ids, str):
            parsed = json.loads(raw_ids)
            destination_ids = tuple(int(item) for item in parsed)
        else:
            destination_ids = ()

        return RelayRecord(
            id=int(row["id"]),
            source_message_id=int(row["source_message_id"]),
            source_channel_id=int(row["source_channel_id"]),
            source_webhook_id=(
                int(row["source_webhook_id"]) if row["source_webhook_id"] is not None else None
            ),
            profile_id=int(row["profile_id"]),
            network_id=int(row["network_id"]),
            destination_channel_id=int(row["destination_channel_id"]),
            destination_message_ids=destination_ids,
            status=RelayStatus(str(row["status"])),
            error_message=str(row["error_message"]) if row["error_message"] is not None else None,
        )
