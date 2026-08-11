from __future__ import annotations

import logging
from collections.abc import Sequence

import discord

logger = logging.getLogger(__name__)


async def align_positions(
    ordered: Sequence[discord.abc.GuildChannel],
    *,
    reason: str,
) -> list[str]:
    """Set each channel's Discord position to its index in ``ordered`` when wrong.

    Discord treats ``position`` as an index among siblings (categories among
    categories; text channels among channels in the same category). Callers pass
    the desired sibling sequence; channels already at the correct index are
    skipped. Returns human-readable failure details for channels that could not
    be moved.
    """
    failures: list[str] = []
    for index, channel in enumerate(ordered):
        current = getattr(channel, "position", None)
        if isinstance(current, int) and current == index:
            continue
        try:
            await channel.edit(position=index, reason=reason)  # type: ignore[attr-defined]
        except discord.HTTPException as exc:
            label = getattr(channel, "name", None) or str(getattr(channel, "id", "?"))
            detail = f"{label}: {exc}"
            failures.append(detail)
            logger.warning(
                "Could not align channel position",
                extra={
                    "channel_id": getattr(channel, "id", None),
                    "desired_position": index,
                    "error": str(exc),
                },
            )
    return failures


async def align_categories_hub_first(
    guild: discord.Guild,
    hub_categories: Sequence[discord.CategoryChannel],
    *,
    reason: str,
) -> list[str]:
    """Place ``hub_categories`` first (in order), then all other guild categories."""
    hub_ids = {category.id for category in hub_categories}
    trailing = sorted(
        (category for category in guild.categories if category.id not in hub_ids),
        key=lambda item: (item.position, item.id),
    )
    return await align_positions([*hub_categories, *trailing], reason=reason)


def next_trailing_position(*, leading_count: int, trailing_count: int) -> int:
    """Absolute Discord position for a new item packed after ``leading_count`` peers."""
    return leading_count + trailing_count
