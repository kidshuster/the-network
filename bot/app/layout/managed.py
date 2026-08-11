from __future__ import annotations

from functools import lru_cache

from bot.app.layout.compiler import DesiredResource, ResourceKind, compile_hub
from bot.app.layout.roles import LayoutContext


@lru_cache(maxsize=1)
def _hub_category_by_id() -> dict[str, tuple[str, tuple[str, ...]]]:
    from bot.app.layout.loader import load_layout

    return {
        key: (value.name, tuple(value.legacy_names))
        for key, value in load_layout().layout.categories.items()
    }


@lru_cache(maxsize=1)
def _hub_channel_by_id() -> dict[str, tuple[str, tuple[str, ...]]]:
    from bot.app.layout.loader import load_layout

    return {
        key: (channel.name, tuple(channel.legacy_names))
        for category in load_layout().layout.categories.values()
        for key, channel in category.channels.items()
    }


def hub_category_name(category_id: str) -> str:
    return _hub_category_by_id()[category_id][0]


def hub_channel_name(channel_id: str) -> str:
    return _hub_channel_by_id()[channel_id][0]


def hub_category_aliases(category_id: str) -> tuple[str, ...]:
    name, legacy = _hub_category_by_id()[category_id]
    return (name, *legacy)


def hub_channel_aliases(channel_id: str) -> tuple[str, ...]:
    name, legacy = _hub_channel_by_id()[channel_id]
    return (name, *legacy)


def hub_category_names() -> frozenset[str]:
    return frozenset(name.casefold() for name, _legacy in _hub_category_by_id().values())


def preserved_channel_names() -> frozenset[str]:
    from bot.app.layout.loader import load_layout

    names: set[str] = set()
    for category in load_layout().layout.categories.values():
        for channel in category.channels.values():
            if channel.lifecycle == "preserve" or channel.community_slot is not None:
                names.add(channel.name.casefold())
    return frozenset(names)


def compile_hub_teardown_resources(context: LayoutContext) -> list[DesiredResource]:
    return [
        resource
        for resource in compile_hub(context)
        if resource.managed == "hub" or resource.kind is ResourceKind.CATEGORY
    ]
