from __future__ import annotations

from functools import lru_cache

from bot.layout.compiler import DesiredResource, ResourceKind, compile_hub
from bot.layout.roles import LayoutContext


@lru_cache(maxsize=1)
def _hub_category_by_id() -> dict[str, str]:
    from bot.layout.loader import load_hub_layout

    return {c.id: c.name for c in load_hub_layout().categories}


@lru_cache(maxsize=1)
def _hub_channel_by_id() -> dict[str, str]:
    from bot.layout.loader import load_hub_layout

    return {c.id: c.name for c in load_hub_layout().channels}


def hub_category_name(category_id: str) -> str:
    return _hub_category_by_id()[category_id]


def hub_channel_name(channel_id: str) -> str:
    return _hub_channel_by_id()[channel_id]


def hub_category_names() -> frozenset[str]:
    return frozenset(name.casefold() for name in _hub_category_by_id().values())


def preserved_channel_names() -> frozenset[str]:
    from bot.layout.loader import load_hub_layout

    names: set[str] = set()
    for channel in load_hub_layout().channels:
        if channel.preserve_on_uninit or channel.community_slot is not None:
            names.add(channel.name.casefold())
            names.update(n.casefold() for n in channel.legacy_names)
    return frozenset(names)


def compile_hub_teardown_resources(context: LayoutContext) -> list[DesiredResource]:
    return [
        resource
        for resource in compile_hub(context)
        if resource.managed == "hub" or resource.kind is ResourceKind.CATEGORY
    ]
