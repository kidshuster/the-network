"""Legacy custom_id helpers kept for tests and sticky message compatibility."""

from __future__ import annotations

_PREFIX = "tn"


def join_network_button() -> str:
    return f"{_PREFIX}:join_network"


def request_approve_button(request_id: int) -> str:
    return f"{_PREFIX}:req_approve:{request_id}"


def request_deny_button(request_id: int) -> str:
    return f"{_PREFIX}:req_deny:{request_id}"


def subscribe_network_button(client_id: int, network_key: str) -> str:
    return f"{_PREFIX}:sub:{client_id}:{network_key}"


def subscribe_connected_button(subscription_id: int) -> str:
    return f"{_PREFIX}:sub_connected:{subscription_id}"


def blacklist_button(subscription_id: int) -> str:
    return f"{_PREFIX}:blacklist:{subscription_id}"


def leave_network_button(subscription_id: int) -> str:
    return f"{_PREFIX}:leave:{subscription_id}"


def timecode_toggle_button(client_id: int) -> str:
    return f"{_PREFIX}:timecode_toggle:{client_id}"


def profile_edit_button(client_id: int) -> str:
    return f"{_PREFIX}:profile_edit:{client_id}"


def delete_client_button(client_id: int) -> str:
    return f"{_PREFIX}:delete_client:{client_id}"


def network_create_button() -> str:
    return f"{_PREFIX}:network_create"


def network_delete_button() -> str:
    return f"{_PREFIX}:network_delete"


def parse_request_action_button(custom_id: str) -> tuple[str, int] | None:
    for action in ("approve", "deny"):
        prefix = f"{_PREFIX}:req_{action}:"
        if custom_id.startswith(prefix):
            try:
                return action, int(custom_id.removeprefix(prefix))
            except ValueError:
                return None
    return None


def parse_subscribe_network_button(custom_id: str) -> tuple[int, str] | None:
    prefix = f"{_PREFIX}:sub:"
    if not custom_id.startswith(prefix):
        return None
    rest = custom_id.removeprefix(prefix)
    if ":" not in rest:
        return None
    client_part, key = rest.split(":", 1)
    try:
        return int(client_part), key.strip().lower()
    except ValueError:
        return None


def parse_join_network_button(custom_id: str) -> bool:
    return custom_id == join_network_button()


def parse_profile_edit_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:profile_edit:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def parse_delete_client_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:delete_client:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def parse_timecode_toggle_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:timecode_toggle:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def parse_subscribe_connected_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:sub_connected:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def parse_blacklist_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:blacklist:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def parse_leave_network_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:leave:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def join_server_button(network_key: str) -> str:
    return f"{_PREFIX}:join:{network_key}"


def parse_join_server_button(custom_id: str) -> str | None:
    prefix = f"{_PREFIX}:join:"
    if not custom_id.startswith(prefix):
        return None
    key = custom_id.removeprefix(prefix).strip().lower()
    return key or None
