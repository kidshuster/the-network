from __future__ import annotations

import discord
from widget_helpers import wire_widget_bot

from bot.app.widgets import render_modal, render_view

SUBSCRIBED_CHANNEL_CONNECTED_LABEL = "Subscribed channel connected"


def test_network_admin_view_has_create_and_delete_buttons() -> None:
    bot = wire_widget_bot()
    view = render_view("network_admin", bot)
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Create Network", "Delete Network", "Delete Client"}


def test_create_network_modal_loads_template_fields() -> None:
    bot = wire_widget_bot()
    modal = render_modal("create_network", bot)
    assert modal.title == "Create network"
    assert "key" in modal._labels
    assert "display_name" in modal._labels


def test_delete_network_modal_loads_template_fields() -> None:
    bot = wire_widget_bot()
    modal = render_modal("delete_network", bot)
    assert modal.title == "Delete network"
    assert "key" in modal._labels


def test_moderator_review_view_has_accept_and_deny() -> None:
    bot = wire_widget_bot()
    view = render_view("moderator_review", bot, request_id=1)
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Accept", "Deny"}


def test_join_network_view_has_join_button() -> None:
    bot = wire_widget_bot()
    view = render_view("join_network", bot)
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Join Network"}


def test_join_network_modal_loads_single_name_field() -> None:
    bot = wire_widget_bot()
    modal = render_modal("join_network", bot)
    assert modal.title == "Join the network"
    assert "server_name" in modal._labels
    assert "profile_image" in modal._labels
    assert "display_name" not in modal._labels
    assert "name" not in modal._labels


def test_subscription_moderation_view_subscribe_connected_button() -> None:
    bot = wire_widget_bot()
    view = render_view(
        "subscription_moderation",
        bot,
        subscription_id=3,
        network_key="stingers",
        show_subscribe_connected=True,
        show_blacklist=False,
    )
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {SUBSCRIBED_CHANNEL_CONNECTED_LABEL, "Leave stingers"}


def test_subscription_moderation_view_not_configured_includes_leave() -> None:
    bot = wire_widget_bot()
    view = render_view(
        "subscription_moderation",
        bot,
        subscription_id=3,
        network_key="stingers",
        show_subscribe_connected=False,
        show_blacklist=False,
    )
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Leave stingers"}


def test_subscribe_setup_view_has_subscribe_connected_button() -> None:
    bot = wire_widget_bot()
    view = render_view("subscribe_setup", bot, subscription_id=3, network_key="stingers")
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {SUBSCRIBED_CHANNEL_CONNECTED_LABEL}


def test_moderation_view_shows_subscribe_connected_before_publish() -> None:
    bot = wire_widget_bot()
    view = render_view(
        "subscription_moderation",
        bot,
        subscription_id=3,
        network_key="stingers",
        show_subscribe_connected=True,
        show_blacklist=False,
    )
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert SUBSCRIBED_CHANNEL_CONNECTED_LABEL in labels
