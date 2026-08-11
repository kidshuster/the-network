from __future__ import annotations

from bot.app.widgets.errors import TemplateRenderError
from bot.app.widgets.models import ActionBinding, Primitive

_PREFIX = "tn1"
_LEGACY = "tn"
_MAX_LEN = 100

_LEGACY_EXACT = {
    "join_network": "ui.modal:join_network",
    "network_create": "ui.modal:create_network",
    "network_delete": "ui.modal:delete_network",
}
_LEGACY_PREFIX = (
    ("req_approve:", "request.approve", "request_id"),
    ("req_deny:", "request.deny", "request_id"),
    ("sub_connected:", "subscription.confirm_connected", "subscription_id"),
    ("blacklist:", "ui.view:blacklist_select", "subscription_id"),
    ("leave:", "subscription.leave", "subscription_id"),
    ("timecode_toggle:", "client.toggle_timecode", "client_id"),
    ("profile_edit:", "ui.modal:edit_client_profile", "client_id"),
    ("delete_client:", "ui.view:delete_client_confirm", "client_id"),
)


def encode(binding: ActionBinding) -> str:
    action = binding.action.strip()
    if not action:
        raise TemplateRenderError("action binding is empty")
    parts = [f"{_PREFIX}:{action}"]
    for key in sorted(binding.arguments):
        value = binding.arguments[key]
        if value is None:
            continue
        encoded = "1" if value is True else "0" if value is False else str(value)
        if any(ch in encoded for ch in (":", "=")):
            raise TemplateRenderError(
                "action argument contains reserved characters",
                element_id=key,
            )
        parts.append(f"{key}={encoded}")
    custom_id = ":".join(parts)
    if len(custom_id) > _MAX_LEN:
        raise TemplateRenderError(
            f"custom_id length {len(custom_id)} exceeds {_MAX_LEN}",
            element_id=action,
        )
    return custom_id


def decode(custom_id: str) -> ActionBinding:
    if custom_id.startswith(f"{_PREFIX}:"):
        return _decode_v1(custom_id)
    if custom_id.startswith(f"{_LEGACY}:"):
        return _decode_legacy(custom_id)
    raise TemplateRenderError("malformed custom_id", element_id=custom_id)


def _decode_v1(custom_id: str) -> ActionBinding:
    rest = custom_id.removeprefix(f"{_PREFIX}:")
    parts = rest.split(":")
    if not parts or not parts[0]:
        raise TemplateRenderError("malformed custom_id", element_id=custom_id)
    action = parts[0]
    if action in {"ui.modal", "ui.view"} and len(parts) >= 2:
        action = f"{action}:{parts[1]}"
        arg_parts = parts[2:]
    else:
        arg_parts = parts[1:]
    arguments: dict[str, Primitive] = {}
    for part in arg_parts:
        if "=" not in part:
            raise TemplateRenderError("malformed custom_id argument", element_id=part)
        key, value = part.split("=", 1)
        arguments[key] = _parse_primitive(value)
    return ActionBinding(action=action, arguments=arguments)


def _parse_primitive(value: str) -> Primitive:
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    return value


def _decode_legacy(custom_id: str) -> ActionBinding:
    rest = custom_id.removeprefix(f"{_LEGACY}:")
    exact = _LEGACY_EXACT.get(rest)
    if exact is not None:
        return ActionBinding(action=exact)
    if rest.startswith("sub:"):
        client_id, network_key = rest.removeprefix("sub:").split(":", 1)
        return ActionBinding(
            action="subscription.create",
            arguments={"client_id": int(client_id), "network_key": network_key},
        )
    for prefix, action, arg in _LEGACY_PREFIX:
        if rest.startswith(prefix):
            return ActionBinding(
                action=action,
                arguments={arg: int(rest.removeprefix(prefix))},
            )
    if rest.startswith("v:"):
        parts = rest.removeprefix("v:").split(":")
        if len(parts) >= 2:
            component = parts[1]
            args = {
                key: _parse_primitive(value)
                for part in parts[2:]
                if "=" in part
                for key, value in [part.split("=", 1)]
            }
            if component == "approve" and "request_id" in args:
                return ActionBinding(action="request.approve", arguments=args)
            if component == "deny" and "request_id" in args:
                return ActionBinding(action="request.deny", arguments=args)
    raise TemplateRenderError("unsupported legacy custom_id", element_id=custom_id)
