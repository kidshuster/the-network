from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from context_helpers import make_test_context

from bot.client import NetworkRelayBot
from bot.ui.join_views import JoinNetworkView, ModeratorReviewView
from bot.ui.network_admin_views import NetworkAdminView
from bot.ui.network_views import NetworkProfileView, SubscribeSetupView, SubscriptionModerationView


@pytest.mark.asyncio
async def test_register_persistent_views_registers_expected_view_types(db) -> None:
    context = make_test_context(db)
    network = await context.network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    client = await context.client_repo.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    await context.client_repo.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=100,
        subscribe_channel_id=101,
    )
    await context.server_request_repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=555,
        server_name="pending",
        display_name="Pending",
        profile_image_url="https://example.com/a.png",
    )
    pending = await context.server_request_repo.list_pending()
    assert len(pending) == 1

    bot = MagicMock(spec=NetworkRelayBot)
    bot.bot_context = context
    added: list[object] = []
    bot.add_view = MagicMock(side_effect=lambda view: added.append(view))

    await NetworkRelayBot._register_persistent_views(bot)

    view_types = {type(view) for view in added}
    assert JoinNetworkView in view_types
    assert NetworkAdminView in view_types
    assert ModeratorReviewView in view_types
    assert NetworkProfileView in view_types
    assert SubscriptionModerationView in view_types
    assert SubscribeSetupView in view_types


@pytest.mark.asyncio
async def test_register_persistent_views_noop_without_context() -> None:
    bot = MagicMock(spec=NetworkRelayBot)
    bot.bot_context = None
    bot.add_view = MagicMock()

    await NetworkRelayBot._register_persistent_views(bot)

    bot.add_view.assert_not_called()
