"""Compose tagged template drafts with recipe handlers (feature-owned)."""

from __future__ import annotations

from typing import Any

from bot.contracts.widgets import ButtonSpec, recipe_handler


def _rh(recipe: str, **kwargs: Any) -> Any:
    return recipe_handler(recipe, **kwargs)

def _view(bot: Any, name: str, binds: dict[str, Any], **values: Any) -> Any:
    draft = bot.templates_view(name, **values)
    for tag, handler in binds.items():
        draft.bind(tag, handler)
    return draft.build(bot)

def build_named_view(bot: Any, name: str, **ctx: Any) -> Any:
    if name == "join_network":
        return _view(bot, name, {"join_button": _rh("request.join.open")})
    if name == "network_admin":
        return _view(
            bot,
            name,
            {
                "create_button": _rh("network.create.open"),
                "delete_button": _rh("network.delete.open"),
                "delete_client_button": _rh("admin.client.delete.open"),
            },
        )
    if name == "moderator_review":
        rid = int(ctx["request_id"])
        return _view(
            bot,
            name,
            {
                "accept_button": _rh("request.approve", request_id=rid),
                "deny_button": _rh("request.deny", request_id=rid),
            },
        )
    if name == "subscribe_setup":
        return _view(
            bot,
            name,
            {
                "confirm_button": _rh(
                    "subscription.confirm_connected",
                    subscription_id=int(ctx["subscription_id"]),
                    network_key=str(ctx["network_key"]),
                ),
            },
        )
    if name == "delete_client_confirm":
        cid = int(ctx["client_id"])
        return _view(
            bot,
            name,
            {
                "confirm_button": _rh("client.delete", client_id=cid),
                "cancel_button": _rh("ui.dismiss"),
            },
        )
    if name == "test_smoke_confirm":
        return _view(
            bot,
            name,
            {
                "confirm_button": _rh(
                    "test.smoke.confirm",
                    recipe_name=str(ctx.get("recipe_name") or ctx.get("recipe") or ""),
                    scenario=str(ctx.get("scenario") or "healthy"),
                ),
                "cancel_button": _rh("test.smoke.cancel"),
            },
        )
    if name == "network_profile":
        cid = int(ctx["client_id"])
        subscribed = set(ctx.get("subscribed_keys") or ())
        draft = bot.templates_view(
            name,
            timecode_state=("On" if ctx.get("timecode_enabled") else "Off"),
            read_only_state=("On" if ctx.get("read_only") else "Off"),
        )
        draft.fill(
            "network_actions",
            [
                ButtonSpec(
                    tag=f"join_{key}",
                    label=f"Join {key}",
                    style="primary",
                    disabled=key in subscribed,
                    handler=_rh("subscription.create", client_id=cid, network_key=key),
                )
                for key in list(ctx.get("network_keys") or [])[:21]
            ],
        )
        for tag, recipe in (
            ("timecode_button", "client.toggle_timecode"),
            ("read_only_button", "client.toggle_read_only"),
            ("edit_button", "client.edit.open"),
            ("delete_button", "client.delete.confirm"),
        ):
            draft.bind(tag, _rh(recipe, client_id=cid))
        return draft.build(bot)
    if name == "subscription_moderation":
        sid, key = int(ctx["subscription_id"]), str(ctx["network_key"])
        actions: list[ButtonSpec] = []
        if ctx.get("show_subscribe_connected"):
            actions.append(
                ButtonSpec(
                    tag="confirm",
                    label="Subscribed channel connected",
                    style="success",
                    handler=_rh(
                        "subscription.confirm_connected",
                        subscription_id=sid,
                        network_key=key,
                    ),
                )
            )
        if ctx.get("show_blacklist"):
            actions.append(
                ButtonSpec(
                    tag="blacklist",
                    label="Blacklist",
                    style="secondary",
                    handler=_rh("subscription.blacklist.open", subscription_id=sid),
                )
            )
        return (
            bot.templates_view(name, network_key=key)
            .fill("actions", actions)
            .bind("leave_button", _rh("subscription.leave", subscription_id=sid, network_key=key))
            .build(bot)
        )
    raise ValueError(f"Unsupported view template {name}")

_MODAL_SUBMITS = {
    "join_network": "request.submit",
    "create_network": "network.create",
    "delete_network": "network.delete",
    "edit_client_profile": "client.edit_profile",
}

def build_named_modal(
    bot: Any,
    name: str,
    *,
    params: dict[str, Any] | None = None,
    field_defaults: dict[str, str] | None = None,
) -> Any:
    recipe = _MODAL_SUBMITS.get(name)
    if recipe is None:
        raise ValueError(f"Unknown modal {name}")
    params = dict(params or {})
    draft = bot.templates_modal(name, **params)
    if field_defaults:
        draft.defaults(**field_defaults)
    draft.on_submit(
        _rh(recipe, **{k: v for k, v in params.items() if isinstance(v, (str, int, bool))})
    )
    return draft.build(bot)
