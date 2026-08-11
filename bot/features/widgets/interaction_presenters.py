from __future__ import annotations

from typing import Any

from bot.contracts.recipes import RecipeContext, recipe
from bot.core.templates import render_embed, render_text


def _require_success(value: object) -> None:
    if getattr(value, "success", True) is False:
        raise ValueError(getattr(value, "error", None) or "Request failed")


async def _embed(response: Any, template: str, **values: Any) -> None:
    await response.send(embed=render_embed(template, **values))


async def _text(response: Any, template: str, **values: Any) -> None:
    await response.send(content=render_text(template, **values))


@recipe("present.request.submit")
async def present_request_submit(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    _require_success(value)
    name = getattr(value, "display_name", None) or getattr(value, "server_name", "") or ""
    await _embed(response, "join_request_submitted", client_name=name)


@recipe("present.request.approve")
async def present_request_approve(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    _require_success(value)
    await _embed(
        response,
        "review_success",
        label="Approved",
        colour="green",
        description=str(getattr(value, "message", None) or "The join request was approved."),
    )


@recipe("present.request.deny")
async def present_request_deny(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    _require_success(value)
    await _embed(
        response,
        "review_success",
        label="Denied",
        colour="red",
        description=str(getattr(value, "message", None) or "The join request was denied."),
    )


@recipe("present.network.create")
async def present_network_create(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    if not (isinstance(value, tuple) and len(value) == 3):
        await response.send(content="Done.")
        return
    network, updated, relinked = value
    await _embed(
        response,
        "network_created",
        key=network.key,
        display_name=network.display_name,
        updated_count=(
            f"Refreshed buttons on **{updated}** client profile(s)." if updated else ""
        ),
        relinked=(
            "Existing client subscriptions were relinked and forwarding resumed."
            if relinked
            else ""
        ),
    )


@recipe("present.network.delete")
async def present_network_delete(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    await _text(response, "network_deleted", key=getattr(value, "key", None) or "")


@recipe("present.client.edit_profile")
async def present_client_edit(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    _require_success(value)
    client = getattr(value, "client", None)
    warnings = getattr(value, "warnings", ()) or ()
    await _embed(
        response,
        "profile_updated",
        display_name=getattr(client, "display_name", ""),
        warnings="\n".join(warnings) if warnings else "",
    )


@recipe("present.client.delete")
async def present_client_delete(
    recipe_context: RecipeContext,
    *,
    response: Any,
    value: object,
    interaction: Any = None,
    **_: Any,
) -> None:
    del recipe_context
    _require_success(value)
    server_name = getattr(value, "server_name", None) or getattr(
        getattr(value, "client", None), "server_name", None
    )
    await _embed(response, "delete_client_success", server_name=server_name or "Client")
    if interaction is not None and getattr(interaction, "message", None) is not None:
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass


@recipe("present.client.toggle_timecode")
async def present_timecode(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    state = "enabled" if getattr(value, "timecode_enabled", False) else "disabled"
    await _text(response, "timecode_toggle_updated", state=state)


@recipe("present.subscription.create")
async def present_subscription_create(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    _require_success(value)
    await _embed(
        response,
        "subscribe_success",
        description=str(getattr(value, "message", None) or "Subscribed."),
    )


@recipe("present.subscription.leave")
async def present_subscription_leave(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    _require_success(value)
    await _embed(
        response,
        "leave_network_success",
        network_key=getattr(value, "network_key", None) or "",
    )


@recipe("present.subscription.confirm_connected")
async def present_subscription_confirm(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context, value
    await _embed(
        response,
        "review_success",
        label="Confirmed",
        colour="green",
        description="Subscribe channel marked as connected.",
    )


@recipe("present.blacklist.replace")
async def present_blacklist(
    recipe_context: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del recipe_context
    await _text(response, "blacklist_updated", count=str(value))
