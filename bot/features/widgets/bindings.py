from __future__ import annotations

import inspect
from typing import Any

from bot.contracts.widgets import ActionBinding, ButtonSpec, SelectOptionSpec, SelectSpec
from bot.core.templates import render_text
from bot.errors import UserFacingError
from bot.features.widgets.guards import (
    require_client_member,
    require_hub_guild,
    require_manage_guild,
)

_MODAL_SUBMIT = {
    "join_network": "request.submit",
    "create_network": "network.create",
    "delete_network": "network.delete",
    "edit_client_profile": "client.edit_profile",
}
_MANAGE_ACTIONS = {"request.approve", "request.deny", "network.create", "network.delete"}
_CLIENT_ACTIONS = {
    "subscription.create": "client_role_required_subscribe",
    "subscription.leave": "client_role_required_leave",
    "subscription.confirm_connected": "client_role_required_subscribe",
    "blacklist.replace": "client_role_required_blacklist",
    "client.edit_profile": "client_role_required_edit",
    "client.delete": "client_role_required_delete",
    "client.toggle_timecode": "client_role_required_edit",
}


def _bind(action: str, **arguments: Any) -> ActionBinding:
    return ActionBinding(action=action, arguments=arguments)


def modal_submit_for(modal_id: str, arguments: dict[str, Any]) -> ActionBinding:
    action = _MODAL_SUBMIT.get(modal_id)
    if action is None:
        raise UserFacingError(f"Unknown modal {modal_id}")
    return ActionBinding(action=action, arguments=arguments)


async def modal_defaults_for(
    bot: Any, modal_id: str, arguments: dict[str, Any]
) -> dict[str, str]:
    if modal_id != "edit_client_profile" or bot.bot_context is None:
        return {}
    client_id = arguments.get("client_id")
    if client_id is None:
        return {}
    client = await bot.bot_context.store.clients.get_by_id(int(client_id))
    return {"display_name": client.display_name} if client is not None else {}


async def blacklist_select_slot(bot: Any, subscription_id: int) -> tuple[SelectSpec, ...]:
    context = bot.bot_context
    if context is None:
        raise UserFacingError(render_text("bot_not_ready"), code="bot_not_ready")
    subscription = await context.store.clients.get_subscription_by_id(subscription_id)
    if subscription is None or subscription.network_id is None:
        raise UserFacingError(render_text("subscription_not_found"), code="subscription_not_found")
    peers = [
        item
        for item in await context.store.clients.list_subscriptions_by_network(
            subscription.network_id
        )
        if item.client_id != subscription.client_id
    ]
    if not peers:
        raise UserFacingError(render_text("no_blacklist_targets"), code="no_blacklist_targets")
    current = set(await context.store.clients.list_blacklisted_client_ids(subscription_id))
    options: list[SelectOptionSpec] = []
    for peer in peers[:25]:
        client = await context.store.clients.get_by_id(peer.client_id)
        if client is None:
            continue
        options.append(
            SelectOptionSpec(
                label=client.display_name[:100],
                value=str(client.id),
                default=client.id in current,
            )
        )
    if not options:
        raise UserFacingError(render_text("no_blacklist_targets"), code="no_blacklist_targets")
    return (
        SelectSpec(
            id="select",
            placeholder="Blacklist clients…",
            options=tuple(options),
            action=_bind("blacklist.replace", subscription_id=subscription_id),
            min_values=0,
            max_values=max(len(options), 1),
        ),
    )


def delete_client_confirm_bindings(client_id: int) -> dict[str, ActionBinding]:
    return {
        "confirm": _bind("client.delete", client_id=client_id),
        "cancel": _bind("ui.dismiss"),
    }


def join_network_bindings() -> dict[str, ActionBinding]:
    return {"join": _bind("ui.modal:join_network")}


def network_admin_bindings() -> dict[str, ActionBinding]:
    return {
        "create": _bind("ui.modal:create_network"),
        "delete": _bind("ui.modal:delete_network"),
    }


def moderator_review_bindings(request_id: int) -> dict[str, ActionBinding]:
    return {
        "approve": _bind("request.approve", request_id=request_id),
        "deny": _bind("request.deny", request_id=request_id),
    }


def subscribe_setup_bindings(subscription_id: int, network_key: str) -> dict[str, ActionBinding]:
    return {
        "confirm": _bind(
            "subscription.confirm_connected",
            subscription_id=subscription_id,
            network_key=network_key,
        )
    }


def network_profile_slots(
    *,
    client_id: int,
    network_keys: list[str],
    subscribed_keys: set[str],
    timecode_enabled: bool = False,
) -> dict[str, tuple[ButtonSpec, ...]]:
    network_actions = tuple(
        ButtonSpec(
            id=f"sub_{key}",
            label=f"Join {key}",
            style="primary",
            disabled=key in subscribed_keys,
            action=_bind("subscription.create", client_id=client_id, network_key=key),
        )
        for key in network_keys[:22]
    )
    profile_actions = (
        ButtonSpec(
            id="timecode",
            label=f"Timecodes: {'On' if timecode_enabled else 'Off'}",
            style="secondary",
            row=4,
            action=_bind("client.toggle_timecode", client_id=client_id),
        ),
        ButtonSpec(
            id="edit",
            label="Edit Profile",
            style="secondary",
            row=4,
            action=_bind("ui.modal:edit_client_profile", client_id=client_id),
        ),
        ButtonSpec(
            id="delete",
            label="Delete Client",
            style="danger",
            row=4,
            action=_bind("ui.view:delete_client_confirm", client_id=client_id),
        ),
    )
    return {"network_actions": network_actions, "profile_actions": profile_actions}


def subscription_moderation_slots(
    *,
    subscription_id: int,
    network_key: str,
    show_subscribe_connected: bool,
    show_blacklist: bool,
) -> dict[str, tuple[ButtonSpec, ...]]:
    actions: list[ButtonSpec] = []
    if show_subscribe_connected:
        actions.append(
            ButtonSpec(
                id="confirm",
                label="Subscribed channel connected",
                style="success",
                action=_bind(
                    "subscription.confirm_connected",
                    subscription_id=subscription_id,
                    network_key=network_key,
                ),
            )
        )
    if show_blacklist:
        actions.append(
            ButtonSpec(
                id="blacklist",
                label="Blacklist",
                style="secondary",
                action=_bind("ui.view:blacklist_select", subscription_id=subscription_id),
            )
        )
    actions.append(
        ButtonSpec(
            id="leave",
            label=f"Leave {network_key}",
            style="danger",
            action=_bind(
                "subscription.leave",
                subscription_id=subscription_id,
                network_key=network_key,
            ),
        )
    )
    return {"actions": tuple(actions)}


async def enrich_trigger_payload(
    bot: Any,
    action: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    context = bot.bot_context
    if context is None:
        raise UserFacingError(render_text("bot_not_ready"), code="bot_not_ready")
    guild = payload.get("guild")
    if guild is not None:
        payload["guild"] = require_hub_guild(bot, guild)

    if "client_id" in payload and "client" not in payload:
        client = await context.store.clients.get_by_id(int(payload["client_id"]))
        if client is None:
            raise UserFacingError(render_text("client_not_found"), code="client_not_found")
        payload["client"] = client

    if "subscription_id" in payload and "subscription" not in payload:
        subscription = await context.store.clients.get_subscription_by_id(
            int(payload["subscription_id"])
        )
        if subscription is None:
            raise UserFacingError(
                render_text("subscription_not_found"),
                code="subscription_not_found",
            )
        payload["subscription"] = subscription
        if "client" not in payload:
            client = await context.store.clients.get_by_id(subscription.client_id)
            if client is None:
                raise UserFacingError(render_text("client_not_found"), code="client_not_found")
            payload["client"] = client

    actor = payload.get("moderator") or payload.get("member") or payload.get("requester")
    if action in _MANAGE_ACTIONS and actor is not None:
        require_manage_guild(actor)
    popup = _CLIENT_ACTIONS.get(action)
    if popup is not None and guild is not None and actor is not None:
        client = payload.get("client")
        if client is not None:
            require_client_member(guild, actor, client, popup=popup, allow_non_member=True)

    subscription = payload.get("subscription")
    if (
        subscription is not None
        and "network" not in payload
        and getattr(subscription, "network_id", None) is not None
    ):
        network = await context.store.networks.get_by_id(subscription.network_id)
        if network is not None:
            payload["network"] = network
            payload.setdefault("network_key", network.key)

    if "network_key" in payload and "network" not in payload:
        network = await context.store.networks.get_by_key(str(payload["network_key"]))
        if network is None:
            raise UserFacingError(
                render_text("network_not_found", network_key=str(payload["network_key"])),
                code="network_not_found",
            )
        payload["network"] = network

    if action == "request.submit" and payload.get("profile_image") is None:
        raise UserFacingError(
            "A profile image is required.",
            title="Request Failed",
            code="profile_image_required",
        )

    function = bot.recipe_registry._recipes.get(action)
    if function is None:
        return payload
    params = inspect.signature(function).parameters
    return {key: value for key, value in payload.items() if key in params}
