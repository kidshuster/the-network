from __future__ import annotations

from bot.app.widgets.errors import TemplateRenderError
from bot.contracts.widgets import Primitive, RecipeHandler

_PREFIX = "tn1"
_LEGACY = "tn"
_MAX_LEN = 100
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


def encode(handler: RecipeHandler) -> str:
    recipe = handler.recipe.strip()
    if not recipe:
        raise TemplateRenderError("recipe handler is empty")
    parts = [f"{_PREFIX}:{recipe}"]
    for key in sorted(handler.arguments):
        value = handler.arguments[key]
        if value is None:
            continue
        encoded = "1" if value is True else "0" if value is False else str(value)
        if any(ch in encoded for ch in (":", "=")):
            raise TemplateRenderError(
                "handler argument contains reserved characters",
                element_id=key,
            )
        parts.append(f"{key}={encoded}")
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
    if custom_id.startswith(f"{_LEGACY}:"):
        return _decode_legacy(custom_id)
    raise TemplateRenderError("malformed custom_id", element_id=custom_id)


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
        mapped = _map_open(recipe, parts[1], parts[2:])
        if mapped is not None:
            return mapped
        raise TemplateRenderError("unsupported ui open custom_id", element_id=custom_id)
    return RecipeHandler(recipe=recipe, arguments=_parse_args(parts[1:]))


def _map_open(kind: str, template_id: str, arg_parts: list[str]) -> RecipeHandler | None:
    recipe = (_OPEN_MODAL if kind == "ui.modal" else _OPEN_VIEW).get(template_id)
    if recipe is None:
        return None
    return RecipeHandler(recipe=recipe, arguments=_parse_args(arg_parts))


def _parse_primitive(value: str) -> Primitive:
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    if value == "1":
        return True
    if value == "0":
        return False
    return value


def _decode_legacy(custom_id: str) -> RecipeHandler:
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
            args = _parse_args([p for p in parts[2:] if "=" in p])
            if component == "approve" and "request_id" in args:
                return RecipeHandler(recipe="request.approve", arguments=args)
            if component == "deny" and "request_id" in args:
                return RecipeHandler(recipe="request.deny", arguments=args)
    raise TemplateRenderError("unsupported legacy custom_id", element_id=custom_id)
