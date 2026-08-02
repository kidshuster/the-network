from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.ui.join_views import JoinNetworkView, ModeratorReviewView
from bot.ui.network_admin_views import CreateNetworkModal, DeleteNetworkModal, NetworkAdminView


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
