from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Network:
    id: int
    key: str
    display_name: str
    feed_category_id: int
    output_channel_id: int
    concat_channel_id: int | None
    profile_forum_channel_id: int | None
    enabled: bool
    join_channel_id: int | None = None
