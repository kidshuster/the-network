"""Small text helpers for Discord display boundaries."""

from __future__ import annotations


def truncate_external_text(text: str, *, limit: int) -> str:
    """Shorten external/user content for a Discord field bound.

    Application-owned template and recipe configuration must be rejected when
    over-limit; use this only for external Discord names/summaries.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return text[: limit - 1] + "…"
