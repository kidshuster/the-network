from __future__ import annotations

from typing import Any

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.core.templates import render_embed, render_text


def _ok(value: object) -> None:
    if getattr(value, "success", True) is False:
        raise ValueError(getattr(value, "error", None) or "Request failed")

async def _embed(response: Any, template: str, **values: Any) -> None:
    await response.send(embed=render_embed(template, **values))

async def _text(response: Any, template: str, **values: Any) -> None:
    await response.send(content=render_text(template, **values))

async def _review(response: Any, *, label: str, colour: str, description: str) -> None:
    await _embed(response, "review_success", label=label, colour=colour, description=description)

@recipe("present.test.smoke.cancel")
async def present_test_smoke_cancel(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    await _text(response, "test_smoke_cancelled")


@recipe("present.request.submit")
async def present_request_submit(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    _ok(value)
    name = getattr(value, "display_name", None) or getattr(value, "server_name", "") or ""
    await _embed(response, "join_request_submitted", client_name=name)

@recipe("present.request.approve")
async def present_request_approve(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    _ok(value)
    await _review(
        response,
        label="Approved",
        colour="green",
        description=str(getattr(value, "message", None) or "The join request was approved."),
    )

@recipe("present.request.deny")
async def present_request_deny(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    _ok(value)
    await _review(
        response,
        label="Denied",
        colour="red",
        description=str(getattr(value, "message", None) or "The join request was denied."),
    )

@recipe("present.network.create")
async def present_network_create(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    if not (isinstance(value, tuple) and len(value) == 3):
        raise ValueError("network.create presenter expected (network, updated, relinked)")
    network, updated, relinked = value
    await _embed(
        response,
        "network_created",
        key=network.key,
        display_name=network.display_name,
        updated_count=f"Refreshed buttons on **{updated}** client profile(s)." if updated else "",
        relinked=(
            "Existing client subscriptions were relinked and forwarding resumed."
            if relinked
            else ""
        ),
    )

@recipe("present.network.delete")
async def present_network_delete(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    await _text(response, "network_deleted", key=getattr(value, "key", None) or "")

@recipe("present.client.edit_profile")
async def present_client_edit(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    _ok(value)
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
    _ctx: RecipeContext, *, response: Any, value: object, interaction: Any = None, **_: Any
) -> None:
    _ok(value)
    server_name = getattr(value, "server_name", None) or getattr(
        getattr(value, "client", None), "server_name", None
    )
    try:
        await _embed(response, "delete_client_success", server_name=server_name or "Client")
    except discord.HTTPException:
        # Deleting a client can remove the channel that owned this interaction.
        pass
    if interaction is not None and getattr(interaction, "message", None) is not None:
        try:
            await interaction.message.edit(view=None)
        except discord.HTTPException:
            pass


@recipe("present.admin.client.delete")
async def present_admin_client_delete(
    ctx: RecipeContext, *, response: Any, value: object, interaction: Any = None, **_: Any
) -> None:
    await present_client_delete(ctx, response=response, value=value, interaction=interaction)

@recipe("present.client.toggle_timecode")
async def present_timecode(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    state = "enabled" if getattr(value, "timecode_enabled", False) else "disabled"
    await _text(response, "timecode_toggle_updated", state=state)

@recipe("present.client.toggle_read_only")
async def present_read_only(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    enabled = bool(getattr(value, "read_only", False))
    state = "on" if enabled else "off"
    detail = "removed" if enabled else "restored for setup"
    await _text(response, "read_only_toggle_updated", state=state, detail=detail)

@recipe("present.subscription.create")
async def present_subscription_create(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    _ok(value)
    await _embed(
        response,
        "subscribe_success",
        description=str(getattr(value, "message", None) or "Subscribed."),
    )

@recipe("present.subscription.leave")
async def present_subscription_leave(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    _ok(value)
    await _embed(
        response, "leave_network_success", network_key=getattr(value, "network_key", None) or ""
    )

@recipe("present.subscription.confirm_connected")
async def present_subscription_confirm(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    del value
    await _review(
        response,
        label="Confirmed",
        colour="green",
        description="Subscribe channel marked as connected.",
    )

@recipe("present.blacklist.replace")
async def present_blacklist(
    _ctx: RecipeContext, *, response: Any, value: object, **_: Any
) -> None:
    await _text(response, "blacklist_updated", count=str(value))
