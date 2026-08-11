from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from context_helpers import make_test_context

from bot.app.bot import NetworkRelayBot
from bot.app.features import build_recipe_registry
from bot.app.widgets import render_view
from bot.app.widgets.dispatch import RenderedView


@pytest.mark.asyncio
async def test_register_persistent_views_registers_expected_view_types(db) -> None:
    context = make_test_context(db)
    network = await context.store.networks.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
    )
    client = await context.store.clients.create(
        guild_id=100,
        server_name="acme",
        display_name="Acme",
        category_id=10,
        client_role_id=11,
        profile_channel_id=30,
        profile_message_id=40,
    )
    await context.store.clients.create_subscription(
        client_id=client.id,
        network_id=network.id,
        network_key=network.key,
        publish_channel_id=100,
        subscribe_channel_id=101,
    )
    await context.store.requests.create(
        guild_id=100,
        network_id=None,
        requester_user_id=555,
        server_name="pending",
        display_name="Pending",
        profile_image_url="https://example.com/a.png",
    )
    pending = await context.store.requests.list_pending()
    assert len(pending) == 1

    from widget_helpers import wire_widget_bot

    bot = wire_widget_bot(MagicMock(spec=NetworkRelayBot))
    bot.bot_context = context
    added: list[object] = []
    bot.add_view = MagicMock(side_effect=lambda view: added.append(view))
    bot.render_view = lambda name, **params: render_view(name, bot, **params)

    await build_recipe_registry(bot).run("app.register_persistent_views")

    assert all(isinstance(view, RenderedView) for view in added)
    view_ids = {view.template_id for view in added if isinstance(view, RenderedView)}
    assert view_ids >= {
        "join_network",
        "network_admin",
        "moderator_review",
        "network_profile",
        "subscription_moderation",
        "subscribe_setup",
    }


@pytest.mark.asyncio
async def test_register_persistent_views_requires_initialized_context() -> None:
    bot = MagicMock(spec=NetworkRelayBot)
    bot.bot_context = None
    bot.add_view = MagicMock()

    registry = build_recipe_registry(bot)
    with pytest.raises(Exception, match="app.register_persistent_views"):
        await registry.run("app.register_persistent_views")

    bot.add_view.assert_not_called()
