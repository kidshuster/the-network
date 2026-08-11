"""Named view/modal composition for hub templates (feature-owned bindings)."""

from __future__ import annotations

from typing import Any

from bot.core.templates import render_text
from bot.errors import UserFacingError
from bot.features.widgets.bindings import (
    delete_client_confirm_bindings,
    join_network_bindings,
    modal_submit_for,
    moderator_review_bindings,
    network_admin_bindings,
    network_profile_slots,
    subscribe_setup_bindings,
    subscription_moderation_slots,
)
from bot.features.widgets.guards import require_client_member, require_manage_guild


def render_named_view(bot: Any, name: str, **context: Any) -> Any:
    if name == "join_network":
        return bot.build_widget_view(name, bindings=join_network_bindings())
    if name == "network_admin":
        return bot.build_widget_view(name, bindings=network_admin_bindings())
    if name == "moderator_review":
        return bot.build_widget_view(
            name,
            bindings=moderator_review_bindings(int(context["request_id"])),
        )
    if name == "subscribe_setup":
        return bot.build_widget_view(
            name,
            bindings=subscribe_setup_bindings(
                int(context["subscription_id"]),
                str(context["network_key"]),
            ),
        )
    if name == "network_profile":
        return bot.build_widget_view(
            name,
            slots=network_profile_slots(
                client_id=int(context["client_id"]),
                network_keys=list(context.get("network_keys") or []),
                subscribed_keys=set(context.get("subscribed_keys") or ()),
                timecode_enabled=bool(context.get("timecode_enabled")),
            ),
        )
    if name == "subscription_moderation":
        return bot.build_widget_view(
            name,
            slots=subscription_moderation_slots(
                subscription_id=int(context["subscription_id"]),
                network_key=str(context["network_key"]),
                show_subscribe_connected=bool(context.get("show_subscribe_connected")),
                show_blacklist=bool(context.get("show_blacklist")),
            ),
        )
    if name == "delete_client_confirm":
        return bot.build_widget_view(
            name,
            bindings=delete_client_confirm_bindings(int(context["client_id"])),
        )
    raise UserFacingError(f"Unsupported view template {name}")


def render_named_modal(
    bot: Any,
    name: str,
    *,
    params: dict[str, Any] | None = None,
    field_defaults: dict[str, str] | None = None,
) -> Any:
    params = dict(params or {})
    return bot.build_widget_modal(
        name,
        values=params,
        defaults=field_defaults,
        submit=modal_submit_for(name, params),
    )


async def build_ui_modal(
    bot: Any,
    modal_id: str,
    arguments: dict[str, Any],
    *,
    actor: Any = None,
) -> Any:
    from bot.features.widgets.bindings import modal_defaults_for

    if modal_id in {"create_network", "delete_network"} and actor is not None:
        require_manage_guild(actor)
    submit = modal_submit_for(modal_id, arguments)
    defaults = {
        key: str(value)
        for key, value in arguments.items()
        if isinstance(value, (str, int))
    }
    defaults.update(await modal_defaults_for(bot, modal_id, arguments))
    return bot.build_widget_modal(
        modal_id,
        values={k: v for k, v in arguments.items() if v is not None},
        defaults=defaults,
        submit=submit,
    )


async def build_ui_view(
    bot: Any,
    view_id: str,
    arguments: dict[str, Any],
    *,
    actor: Any = None,
    guild: Any = None,
) -> dict[str, Any]:
    from bot.features.widgets.bindings import blacklist_select_slot

    if view_id == "delete_client_confirm":
        client_id = int(arguments["client_id"])
        context = bot.bot_context
        if context is None:
            raise UserFacingError(render_text("bot_not_ready"), code="bot_not_ready")
        client = await context.store.clients.get_by_id(client_id)
        if client is None:
            raise UserFacingError(render_text("client_not_found"), code="client_not_found")
        if guild is not None and actor is not None:
            require_client_member(
                guild,
                actor,
                client,
                popup="client_role_required_delete",
                allow_non_member=True,
            )
        return {
            "content": render_text(
                "delete_client_confirm_prompt",
                server_name=client.server_name,
            ),
            "view": bot.build_widget_view(
                view_id,
                bindings=delete_client_confirm_bindings(client_id),
            ),
        }
    if view_id == "blacklist_select":
        return {
            "content": render_text("blacklist_select_prompt"),
            "view": bot.build_widget_view(
                view_id,
                slots={
                    "blacklist": await blacklist_select_slot(
                        bot, int(arguments["subscription_id"])
                    )
                },
            ),
        }
    raise UserFacingError(f"Unknown ui.view {view_id}")

