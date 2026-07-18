from __future__ import annotations

from dataclasses import dataclass

from bot.domain.network import Network


@dataclass(frozen=True)
class CategoryRoute:
    """Maps a feed category to its network output (Phase 2 — no profile yet)."""

    feed_category_id: int
    network: Network
    output_channel_id: int
    concat_channel_id: int | None
