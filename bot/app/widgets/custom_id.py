"""Versioned recipe custom-ID codec (``tn1:<recipe>:k=<typed>``).

Typed values are marked with a leading ``!`` and never contain ``:``:
- ``!n`` → None
- ``!b1`` / ``!b0`` → bool
- ``!i<digits>`` → int
- ``!s<text>`` → str

Values without ``!`` are transitional untyped tn1 segments.
"""

from __future__ import annotations

from bot.app.widgets.custom_id_legacy import (
    decode_legacy_prefix,
    map_transitional_open,
    parse_untyped_primitive,
)
from bot.app.widgets.errors import TemplateRenderError
from bot.contracts.widgets import Primitive, RecipeHandler

_PREFIX = "tn1"
_MAX_LEN = 100


def encode(handler: RecipeHandler) -> str:
    recipe = handler.recipe.strip()
    if not recipe:
        raise TemplateRenderError("recipe handler is empty")
    if ":" in recipe:
        raise TemplateRenderError(
            "recipe name must not contain ':'",
            element_id=recipe,
        )
    parts = [f"{_PREFIX}:{recipe}"]
    for key in sorted(handler.arguments):
        parts.append(f"{key}={_encode_primitive(handler.arguments[key], key=key)}")
    custom_id = ":".join(parts)
    if len(custom_id) > _MAX_LEN:
        raise TemplateRenderError(
            f"custom_id length {len(custom_id)} exceeds {_MAX_LEN}",
            element_id=recipe,
        )
    return custom_id


def decode(custom_id: str) -> RecipeHandler:
    if custom_id.startswith(f"{_PREFIX}:"):
        return _decode_v1(custom_id)
    legacy = decode_legacy_prefix(custom_id)
    if legacy is not None:
        return legacy
    raise TemplateRenderError("malformed custom_id", element_id=custom_id)


def _encode_primitive(value: Primitive, *, key: str) -> str:
    if value is None:
        return "!n"
    if value is True:
        return "!b1"
    if value is False:
        return "!b0"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"!i{value}"
    if isinstance(value, str):
        if any(ch in value for ch in (":", "=")):
            raise TemplateRenderError(
                "handler argument contains reserved characters",
                element_id=key,
            )
        return f"!s{value}"
    raise TemplateRenderError(
        f"handler argument {key!r} has unsupported type",
        element_id=key,
    )


def _parse_primitive(value: str) -> Primitive:
    if not value.startswith("!"):
        return parse_untyped_primitive(value)
    typed = value[1:]
    if typed == "n":
        return None
    if typed == "b1":
        return True
    if typed == "b0":
        return False
    if typed.startswith("i"):
        raw = typed[1:]
        if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
            return int(raw)
        raise TemplateRenderError("malformed int custom_id value", element_id=value)
    if typed.startswith("s"):
        return typed[1:]
    raise TemplateRenderError("malformed typed custom_id value", element_id=value)


def _parse_args(parts: list[str]) -> dict[str, Primitive]:
    arguments: dict[str, Primitive] = {}
    for part in parts:
        if "=" not in part:
            raise TemplateRenderError("malformed custom_id argument", element_id=part)
        key, value = part.split("=", 1)
        arguments[key] = _parse_primitive(value)
    return arguments


def _decode_v1(custom_id: str) -> RecipeHandler:
    rest = custom_id.removeprefix(f"{_PREFIX}:")
    parts = rest.split(":")
    if not parts or not parts[0]:
        raise TemplateRenderError("malformed custom_id", element_id=custom_id)
    recipe = parts[0]
    if recipe in {"ui.modal", "ui.view"} and len(parts) >= 2:
        mapped = map_transitional_open(recipe, parts[1], parts[2:])
        if mapped is not None:
            return mapped
        raise TemplateRenderError("unsupported ui open custom_id", element_id=custom_id)
    return RecipeHandler(recipe=recipe, arguments=_parse_args(parts[1:]))
