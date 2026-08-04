from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.ui.join_views import JoinNetworkModal, JoinNetworkView, ModeratorReviewView
from bot.ui.network_admin_views import CreateNetworkModal, DeleteNetworkModal, NetworkAdminView
from bot.ui.network_views import SubscribeSetupView, SubscriptionModerationView


def test_network_admin_view_has_create_and_delete_buttons() -> None:
    bot = MagicMock()
    view = NetworkAdminView(bot)
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Create Network", "Delete Network"}


def test_create_network_modal_loads_template_fields() -> None:
    bot = MagicMock()
    modal = CreateNetworkModal(bot)
    assert modal.title == "Create network"
    assert "key" in modal._fields
    assert "display_name" in modal._fields


def test_delete_network_modal_loads_template_fields() -> None:
    bot = MagicMock()
    modal = DeleteNetworkModal(bot)
    assert modal.title == "Delete network"
    assert "key" in modal._fields


@pytest.mark.asyncio
async def test_moderator_review_view_has_accept_and_deny() -> None:
    bot = MagicMock()
    view = ModeratorReviewView(bot, request_id=1)
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Accept", "Deny"}


def test_join_network_view_has_join_button() -> None:
    bot = MagicMock()
    view = JoinNetworkView(bot)
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Join Network"}


def test_join_network_modal_loads_single_name_field() -> None:
    bot = MagicMock()
    modal = JoinNetworkModal(bot)
    assert modal.title == "Join the network"
    assert "name" in modal._fields
    assert "profile_image" in modal._fields
    assert "display_name" not in modal._fields
    assert "server_name" not in modal._fields

def test_subscription_moderation_view_subscribe_connected_button() -> None:
    bot = MagicMock()
    view = SubscriptionModerationView(
        bot,
        subscription_id=3,
        network_key="stingers",
        show_subscribe_connected=True,
        show_blacklist=False,
    )
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Subscribe connected", "Leave stingers"}


def test_subscription_moderation_view_not_configured_includes_leave() -> None:
    bot = MagicMock()
    view = SubscriptionModerationView(
        bot,
        subscription_id=3,
        network_key="stingers",
        show_subscribe_connected=False,
        show_blacklist=False,
    )
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Leave stingers"}


def test_subscribe_setup_view_has_subscribe_connected_button() -> None:
    bot = MagicMock()
    view = SubscribeSetupView(bot, subscription_id=3, network_key="stingers")
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert labels == {"Subscribe connected"}


def test_moderation_view_shows_subscribe_connected_before_publish() -> None:
    bot = MagicMock()
    view = SubscriptionModerationView(
        bot,
        subscription_id=3,
        network_key="stingers",
        show_subscribe_connected=True,
        show_blacklist=False,
    )
    labels = {child.label for child in view.children if isinstance(child, discord.ui.Button)}
    assert "Subscribe connected" in labels
