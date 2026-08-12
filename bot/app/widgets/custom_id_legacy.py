"""Read-only legacy custom-ID decode (pre-tn1 / transitional open maps).

Removal condition: delete this module and its call from ``custom_id.decode`` after the
next sticky rewrite cycle once no managed persistent message still carries a ``tn:``
prefix or a transitional ``tn1:ui.modal`` / ``tn1:ui.view`` custom ID. Confirm by
grepping deployed message custom IDs (or re-rendering all stickies and waiting one
release with no legacy decode hits in logs).
"""

from __future__ import annotations

from bot.app.widgets.errors import TemplateRenderError
from bot.contracts.widgets import Primitive, RecipeHandler

_LEGACY = "tn"
_LEGACY_EXACT = {
    "join_network": "request.join.open",
    "network_create": "network.create.open",
    "network_delete": "network.delete.open",
}
_LEGACY_PREFIX = (
    ("req_approve:", "request.approve", "request_id"),
    ("req_deny:", "request.deny", "request_id"),
    ("sub_connected:", "subscription.confirm_connected", "subscription_id"),
    ("blacklist:", "subscription.blacklist.open", "subscription_id"),
    ("leave:", "subscription.leave", "subscription_id"),
    ("timecode_toggle:", "client.toggle_timecode", "client_id"),
    ("profile_edit:", "client.edit.open", "client_id"),
    ("delete_client:", "client.delete.confirm", "client_id"),
)
_OPEN_MODAL = {
    "join_network": "request.join.open",
    "create_network": "network.create.open",
    "delete_network": "network.delete.open",
    "edit_client_profile": "client.edit.open",
}
_OPEN_VIEW = {
    "delete_client_confirm": "client.delete.confirm",
    "blacklist_select": "subscription.blacklist.open",
}


def decode_legacy_prefix(custom_id: str) -> RecipeHandler | None:
    """Decode ``tn:...`` IDs. Returns None when the string is not legacy-prefixed."""
    if not custom_id.startswith(f"{_LEGACY}:"):
        return None
    rest = custom_id.removeprefix(f"{_LEGACY}:")
    exact = _LEGACY_EXACT.get(rest)
    if exact is not None:
        return RecipeHandler(recipe=exact)
    if rest.startswith("sub:"):
        client_id, network_key = rest.removeprefix("sub:").split(":", 1)
        return RecipeHandler(
            recipe="subscription.create",
            arguments={"client_id": int(client_id), "network_key": network_key},
        )
    for prefix, recipe, arg in _LEGACY_PREFIX:
        if rest.startswith(prefix):
            return RecipeHandler(
                recipe=recipe,
                arguments={arg: int(rest.removeprefix(prefix))},
            )
    if rest.startswith("v:"):
        parts = rest.removeprefix("v:").split(":")
        if len(parts) >= 2:
            component = parts[1]
            args = _parse_untyped([p for p in parts[2:] if "=" in p])
            if component == "approve" and "request_id" in args:
                return RecipeHandler(recipe="request.approve", arguments=args)
            if component == "deny" and "request_id" in args:
                return RecipeHandler(recipe="request.deny", arguments=args)
    raise TemplateRenderError("unsupported legacy custom_id", element_id=custom_id)


def map_transitional_open(
    kind: str, template_id: str, arg_parts: list[str]
) -> RecipeHandler | None:
    """Map leftover ``tn1:ui.modal|ui.view:...`` IDs to open recipes."""
    recipe = (_OPEN_MODAL if kind == "ui.modal" else _OPEN_VIEW).get(template_id)
    if recipe is None:
        return None
    return RecipeHandler(recipe=recipe, arguments=_parse_untyped(arg_parts))


def parse_untyped_primitive(value: str) -> Primitive:
    """Best-effort parse for legacy untyped ``k=v`` segments (no bool from 0/1)."""
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    return value


def _parse_untyped(parts: list[str]) -> dict[str, Primitive]:
    arguments: dict[str, Primitive] = {}
    for part in parts:
        if "=" not in part:
            raise TemplateRenderError("malformed custom_id argument", element_id=part)
        key, value = part.split("=", 1)
        arguments[key] = parse_untyped_primitive(value)
    return arguments
