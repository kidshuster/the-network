from __future__ import annotations

from unittest.mock import MagicMock

import discord


def make_test_view_registry() -> MagicMock:
    """Return a ViewRegistry mock that yields lightweight stand-in views."""
    registry = MagicMock()

    def _view() -> discord.ui.View:
        return MagicMock(spec=discord.ui.View)

    def _profile_view(
        _client_id: int,
        _network_keys: list[str],
        **kwargs: object,
    ) -> discord.ui.View:
        return _view()

    registry.register_join_network_view.side_effect = _view
    registry.register_network_admin_view.side_effect = _view
    registry.register_moderator_review_view.side_effect = lambda _request_id: _view()
    registry.register_client_profile_view.side_effect = _profile_view
    registry.register_subscribe_setup_view.side_effect = lambda _subscription_id, _network_key: (
        _view()
    )
    registry.register_subscription_moderation_view.side_effect = (
        lambda _subscription, _network, _setup_state: _view()
    )
    registry.register_client_profile_for_client.side_effect = lambda _client, _network_keys: _view()
    return registry
