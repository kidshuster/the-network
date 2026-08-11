from __future__ import annotations

from functools import lru_cache

from bot.channels.layout.compiler import DesiredResource, ResourceKind, compile_hub
from bot.channels.layout.roles import LayoutContext


@lru_cache(maxsize=1)
def _hub_category_by_id() -> dict[str, str]:
    from bot.channels.layout.loader import load_layout

    return {key: value.name for key, value in load_layout().layout.categories.items()}


@lru_cache(maxsize=1)
def _hub_channel_by_id() -> dict[str, tuple[str, tuple[str, ...]]]:
    from bot.channels.layout.loader import load_layout

    return {
        key: (channel.name, tuple(channel.legacy_names))
        for category in load_layout().layout.categories.values()
        for key, channel in category.channels.items()
    }


def hub_category_name(category_id: str) -> str:
    return _hub_category_by_id()[category_id]


def hub_channel_name(channel_id: str) -> str:
    return _hub_channel_by_id()[channel_id][0]


def hub_category_aliases(category_id: str) -> tuple[str, ...]:
    """Current category display name (single entry; categories have no legacy list)."""
    return (hub_category_name(category_id),)


def hub_channel_aliases(channel_id: str) -> tuple[str, ...]:
    """Current channel display name plus YAML legacy_names for resolution after renames."""
    name, legacy = _hub_channel_by_id()[channel_id]
    aliases: list[str] = [name]
    for item in legacy:
        if item.casefold() not in {alias.casefold() for alias in aliases}:
            aliases.append(item)
    return tuple(aliases)


def hub_category_names() -> frozenset[str]:
    return frozenset(name.casefold() for name in _hub_category_by_id().values())


def preserved_channel_names() -> frozenset[str]:
    from bot.channels.layout.loader import load_layout

    names: set[str] = set()
    for category in load_layout().layout.categories.values():
        for channel in category.channels.values():
            if channel.lifecycle == "preserve" or channel.community_slot is not None:
                names.add(channel.name.casefold())
                names.update(n.casefold() for n in channel.legacy_names)
    return frozenset(names)


def compile_hub_teardown_resources(context: LayoutContext) -> list[DesiredResource]:
    return [
        resource
        for resource in compile_hub(context)
        if resource.managed == "hub" or resource.kind is ResourceKind.CATEGORY
    ]
