from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import discord


def bind_item_callback(
    item: discord.ui.Item[Any],
    callback: Callable[[discord.Interaction], Coroutine[Any, Any, None]],
) -> None:
    """Assign a discord.py view item callback (stubs mark callback as read-only)."""
    item.callback = callback  # type: ignore[method-assign, assignment]
