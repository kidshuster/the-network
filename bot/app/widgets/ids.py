from __future__ import annotations

from typing import Any

_PREFIX = "tn"


def encode_component(
    view_id: str,
    component_id: str,
    params: dict[str, str | int] | None = None,
) -> str:
    """Encode view+component (+ optional params) into a Discord custom_id."""
    view = view_id.replace(".", "-")
    component = component_id.replace(".", "-")
    base = f"{_PREFIX}:v:{view}:{component}"
    if not params:
        return base
    parts = [f"{key}={value}" for key, value in sorted(params.items())]
    return base + ":" + ":".join(parts)


def parse_component(custom_id: str) -> tuple[str, str, dict[str, str]] | None:
    prefix = f"{_PREFIX}:v:"
    if not custom_id.startswith(prefix):
        return None
    rest = custom_id.removeprefix(prefix)
    parts = rest.split(":")
    if len(parts) < 2:
        return None
    view_id = parts[0].replace("-", ".")
    component_id = parts[1].replace("-", ".")
    params: dict[str, str] = {}
    for part in parts[2:]:
        if "=" in part:
            key, value = part.split("=", 1)
            params[key] = value
        else:
            params[f"_{len(params)}"] = part
    return view_id, component_id, params


def format_custom_id(template: str, params: dict[str, Any]) -> str:
    """Substitute ``{name}`` placeholders in an explicit custom_id template."""
    result = template
    for key, value in params.items():
        result = result.replace("{" + key + "}", str(value))
    return result
