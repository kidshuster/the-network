from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from bot.core.channels.stickies.schema import StickyCatalog, StickySpec

_CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "widgets"
    / "channels"
    / "stickies"
    / "stickies.yaml"
)


class StickyConfigurationError(ValueError):
    pass


@lru_cache(maxsize=1)
def load_sticky_catalog() -> StickyCatalog:
    try:
        with _CATALOG_PATH.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        return StickyCatalog.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise StickyConfigurationError(f"Invalid sticky catalog: {exc}") from exc


def sticky_spec(sticky_id: str) -> StickySpec:
    try:
        return load_sticky_catalog().stickies[sticky_id]
    except KeyError as exc:
        raise StickyConfigurationError(f"Unknown sticky: {sticky_id}") from exc


def validate_sticky_catalog() -> None:
    catalog = load_sticky_catalog()
    for sticky_id, spec in catalog.stickies.items():
        if spec.strategy != "scoped" and spec.settings_key is None:
            raise StickyConfigurationError(
                f"{sticky_id}: non-scoped sticky requires settings_key"
            )
