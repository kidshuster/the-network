from __future__ import annotations

from bot.core.channels.stickies import load_sticky_catalog, validate_sticky_catalog
from bot.core.widgets import load_template


def test_sticky_catalog_references_valid_templates() -> None:
    validate_sticky_catalog()
    catalog = load_sticky_catalog()
    assert catalog.stickies
    for spec in catalog.stickies.values():
        load_template(spec.template)


def test_persistent_sticky_settings_keys_are_unique() -> None:
    catalog = load_sticky_catalog()
    keys = [spec.settings_key for spec in catalog.stickies.values() if spec.settings_key]
    assert len(keys) == len(set(keys))
