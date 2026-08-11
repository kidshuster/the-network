from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from bot.channels.layout.schema import LayoutSpec, RolesSpec

_LAYOUT_DIR = Path(__file__).resolve().parent
_cache: dict[str, BaseModel] = {}


class LayoutTemplateError(Exception):
    pass


def _load[Spec: BaseModel](path: Path, model: type[Spec]) -> Spec:
    try:
        with path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise LayoutTemplateError(f"{path.name}: expected mapping at root")
        return model.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise LayoutTemplateError(f"{path.name}: {exc}") from exc


def clear_layout_cache() -> None:
    _cache.clear()
    from bot.channels.layout.managed import _hub_category_by_id, _hub_channel_by_id

    _hub_category_by_id.cache_clear()
    _hub_channel_by_id.cache_clear()


def load_roles() -> RolesSpec:
    cached = _cache.get("roles")
    if isinstance(cached, RolesSpec):
        return cached
    spec = _load(_LAYOUT_DIR / "roles.yaml", RolesSpec)
    _cache["roles"] = spec
    return spec


def load_layout() -> LayoutSpec:
    cached = _cache.get("layout")
    if isinstance(cached, LayoutSpec):
        return cached
    spec = _load(_LAYOUT_DIR / "layout.yaml", LayoutSpec)
    _cache["layout"] = spec
    return spec


def validate_all_layouts() -> None:
    """Fail before Discord mutation when either configuration is invalid."""
    clear_layout_cache()
    roles = load_roles()
    layout = load_layout()
    known_roles = set(roles.roles)
    for profile_name, profile in layout.permission_profiles.items():
        unknown = (set(profile.roles) | set(profile.overrides)) - known_roles
        if unknown:
            raise LayoutTemplateError(
                f"profile {profile_name!r}: unknown logical roles {sorted(unknown)}",
            )
    resources = [
        *layout.layout.categories.items(),
        ("client_category", layout.layout.client_category),
    ]
    for category_id, category in resources:
        profile = layout.permission_profiles[category.profile]
        unknown = set(category.overrides) - set(profile.roles)
        if unknown:
            raise LayoutTemplateError(
                f"category {category_id!r}: overrides roles outside profile {sorted(unknown)}",
            )
        for channel_id, channel in category.channels.items():
            selected = layout.permission_profiles[channel.profile or category.profile]
            unknown = set(channel.overrides) - set(selected.roles)
            if unknown:
                raise LayoutTemplateError(
                    f"channel {channel_id!r}: overrides roles outside profile {sorted(unknown)}",
                )
