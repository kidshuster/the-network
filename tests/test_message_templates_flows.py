from __future__ import annotations

from bot.presentation import render_embed, render_text


def test_join_request_submitted_renders_server_name() -> None:
    embed = render_embed(
        "join_request_submitted",
        client_name="Acme Corp",
    )
    assert any("Acme Corp" in (field.value or "") for field in embed.fields)


def test_join_request_moderator_includes_request_fields() -> None:
    embed = render_embed(
        "join_request_moderator",
        requester_mention="<@123>",
        client_name="Acme",
        request_id="42",
    )
    field_names = {field.name for field in embed.fields}
    assert "Requester" in field_names
    assert "Name" in field_names


def test_review_success_accepts_label() -> None:
    embed = render_embed(
        "review_success",
        label="Accepted",
        colour="green",
        description="Done.",
    )
    assert embed.title == "Request Accepted"
    assert embed.description == "Done."


def test_success_and_central_error_templates() -> None:
    success = render_embed("subscribe_success", description="Subscribed to stingers.")
    failed = render_embed(
        "error",
        title="Subscribe Failed",
        description="Missing Permissions",
        reference="abc123",
    )
    assert success.title == "Network Subscription"
    assert failed.title == "Subscribe Failed"
    assert "Missing Permissions" in (failed.description or "")


def test_central_error_supports_dynamic_operation_title() -> None:
    embed = render_embed(
        "error",
        title="Server Init Failed",
        description="Join-approval provisioning probe failed",
        reference="abc123",
    )
    assert embed.title == "Server Init Failed"
    assert "provisioning probe" in (embed.description or "")


def test_client_role_required_popups_non_empty() -> None:
    for name in (
        "client_role_required_subscribe",
        "client_role_required_edit",
        "client_role_required_delete",
    ):
        text = render_text(name)
        assert text.strip()
        assert len(text) <= 2000


def test_manage_guild_required_popup() -> None:
    text = render_text("manage_guild_required")
    assert "Manage Server" in text or "manage" in text.casefold()


def test_leave_network_success_template() -> None:
    embed = render_embed(
        "leave_network_success",
        network_key="stingers",
    )
    assert "stingers" in (embed.description or "")
