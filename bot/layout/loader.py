from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from bot.layout.schema import (
    ClientLayoutSpec,
    HubLayoutSpec,
    PermissionPresetsSpec,
)

_LAYOUT_DIR = Path(__file__).resolve().parent

_cache: dict[str, Any] = {}


class LayoutTemplateError(Exception):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise LayoutTemplateError(f"{path.name}: expected mapping at root")
    return raw


def clear_layout_cache() -> None:
    _cache.clear()
    from bot.layout.managed import _hub_category_by_id, _hub_channel_by_id

    _hub_category_by_id.cache_clear()
    _hub_channel_by_id.cache_clear()


def load_presets() -> PermissionPresetsSpec:
    cached = _cache.get("presets")
    if isinstance(cached, PermissionPresetsSpec):
        return cached
    path = _LAYOUT_DIR / "presets.yaml"
    try:
        spec = PermissionPresetsSpec.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise LayoutTemplateError(f"presets.yaml: {exc}") from exc
    _cache["presets"] = spec
    return spec


def load_hub_layout() -> HubLayoutSpec:
    cached = _cache.get("hub")
    if isinstance(cached, HubLayoutSpec):
        return cached
    path = _LAYOUT_DIR / "hub.yaml"
    try:
        spec = HubLayoutSpec.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise LayoutTemplateError(f"hub.yaml: {exc}") from exc
    _cache["hub"] = spec
    return spec


def load_client_layout() -> ClientLayoutSpec:
    cached = _cache.get("client")
    if isinstance(cached, ClientLayoutSpec):
        return cached
    path = _LAYOUT_DIR / "client.yaml"
    try:
        spec = ClientLayoutSpec.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise LayoutTemplateError(f"client.yaml: {exc}") from exc
    _cache["client"] = spec
    return spec


def validate_all_layouts() -> None:
    """Fail-fast startup validation for every layout YAML."""
    clear_layout_cache()
    presets = load_presets()
    hub = load_hub_layout()
    client = load_client_layout()
    known = set(presets.presets)
    for category in hub.categories:
        for binding in category.overwrites:
            if binding.preset not in known:
                raise LayoutTemplateError(
                    f"hub category {category.id}: unknown preset {binding.preset!r}",
                )
    for channel in hub.channels:
        for binding in channel.overwrites:
            if binding.preset not in known:
                raise LayoutTemplateError(
                    f"hub channel {channel.id}: unknown preset {binding.preset!r}",
                )
    for binding in client.category.overwrites:
        if binding.preset not in known:
            raise LayoutTemplateError(
                f"client category: unknown preset {binding.preset!r}",
            )
    for channel in client.channels:
        for binding in channel.overwrites:
            if binding.preset not in known:
                raise LayoutTemplateError(
                    f"client channel {channel.id}: unknown preset {binding.preset!r}",
                )
