from __future__ import annotations

from collections.abc import Callable, Iterable

import discord

from bot.errors import UserFacingError

ChannelPredicate = Callable[[discord.abc.GuildChannel], bool]


class ChannelLookupError(UserFacingError):
    """A configured channel could not be resolved without guessing."""

    def __init__(self, names: Iterable[str]) -> None:
        candidates = tuple(names)
        rendered = ", ".join(f"#{name}" for name in candidates)
        super().__init__(
            f"Required channel {rendered or '(unnamed)'} was not found. "
            "Run `/server init` to reconcile the server layout, then retry.",
            title="Channel Unavailable",
            code="channel_not_found",
        )
        self.names = candidates


def _channel_names(names: str | Iterable[str]) -> tuple[str, ...]:
    candidates = (names,) if isinstance(names, str) else tuple(names)
    return tuple(name.strip() for name in candidates if name.strip())


def find_channel[ChannelT: discord.abc.GuildChannel](
    guild: discord.Guild,
    names: str | Iterable[str],
    *,
    channel_type: type[ChannelT],
    category_id: int | None = None,
    predicate: ChannelPredicate | None = None,
) -> ChannelT | None:
    """Find a configured channel without assuming it exists."""
    candidates = _channel_names(names)
    if issubclass(channel_type, discord.CategoryChannel):
        channels: Iterable[discord.abc.GuildChannel] = (*guild.categories, *guild.channels)
    elif issubclass(channel_type, discord.TextChannel):
        channels = (*guild.text_channels, *guild.channels)
    else:
        channels = guild.channels
    for name in candidates:
        target = name.casefold()
        for channel in channels:
            if not isinstance(channel, channel_type):
                continue
            if channel.name.casefold() != target:
                continue
            if category_id is not None and channel.category_id != category_id:
                continue
            if predicate is not None and not predicate(channel):
                continue
            return channel
    return None


def require_channel[ChannelT: discord.abc.GuildChannel](
    guild: discord.Guild,
    names: str | Iterable[str],
    *,
    channel_type: type[ChannelT],
    category_id: int | None = None,
    predicate: ChannelPredicate | None = None,
) -> ChannelT:
    candidates = _channel_names(names)
    channel = find_channel(
        guild,
        candidates,
        channel_type=channel_type,
        category_id=category_id,
        predicate=predicate,
    )
    if channel is None:
        raise ChannelLookupError(candidates)
    return channel
