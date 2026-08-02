from __future__ import annotations

_PREFIX = "tn"


def join_network_button() -> str:
    return f"{_PREFIX}:join_network"


def parse_join_network_button(custom_id: str) -> bool:
    return custom_id == join_network_button()


def join_server_button(network_key: str) -> str:
    """Legacy per-network join button."""
    return f"{_PREFIX}:join:{network_key}"


def parse_join_server_button(custom_id: str) -> str | None:
    prefix = f"{_PREFIX}:join:"
    if not custom_id.startswith(prefix):
        return None
    key = custom_id.removeprefix(prefix).strip().lower()
    return key or None


def subscribe_network_button(client_id: int, network_key: str) -> str:
    return f"{_PREFIX}:sub:{client_id}:{network_key}"


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


def subscribe_connected_button(subscription_id: int) -> str:
    return f"{_PREFIX}:sub_connected:{subscription_id}"


def parse_subscribe_connected_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:sub_connected:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def blacklist_button(subscription_id: int) -> str:
    return f"{_PREFIX}:blacklist:{subscription_id}"


def parse_blacklist_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:blacklist:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def leave_network_button(subscription_id: int) -> str:
    return f"{_PREFIX}:leave:{subscription_id}"


def parse_leave_network_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:leave:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def profile_edit_button(client_id: int) -> str:
    return f"{_PREFIX}:profile_edit:{client_id}"


def delete_client_button(client_id: int) -> str:
    return f"{_PREFIX}:delete_client:{client_id}"


def parse_delete_client_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:delete_client:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def network_create_button() -> str:
    return f"{_PREFIX}:network_create"


def network_delete_button() -> str:
    return f"{_PREFIX}:network_delete"


def parse_profile_edit_button(custom_id: str) -> int | None:
    prefix = f"{_PREFIX}:profile_edit:"
    if not custom_id.startswith(prefix):
        return None
    try:
        return int(custom_id.removeprefix(prefix))
    except ValueError:
        return None


def request_approve_button(request_id: int) -> str:
    return f"{_PREFIX}:req_approve:{request_id}"


def request_deny_button(request_id: int) -> str:
    return f"{_PREFIX}:req_deny:{request_id}"


def parse_request_action_button(custom_id: str) -> tuple[str, int] | None:
    for action in ("approve", "deny"):
        prefix = f"{_PREFIX}:req_{action}:"
        if custom_id.startswith(prefix):
            try:
                return action, int(custom_id.removeprefix(prefix))
            except ValueError:
                return None
    return None
