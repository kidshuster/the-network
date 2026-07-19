from __future__ import annotations

_PREFIX = "tn"


def join_server_button(network_key: str) -> str:
    return f"{_PREFIX}:join:{network_key}"


def parse_join_server_button(custom_id: str) -> str | None:
    prefix = f"{_PREFIX}:join:"
    if not custom_id.startswith(prefix):
        return None
    key = custom_id.removeprefix(prefix).strip().lower()
    return key or None


def profile_edit_button(profile_channel_id: int) -> str:
    return f"{_PREFIX}:profile_edit:{profile_channel_id}"


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
