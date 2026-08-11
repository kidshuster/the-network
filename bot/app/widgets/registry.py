from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from bot.core.clients.setup_state import SubscriptionSetupState
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.network import Network

if TYPE_CHECKING:
    import discord

    from bot.app.bot import NetworkRelayBot


class PersistentViewRegistry:
    """Build and register declarative persistent views for hub stickies."""

    def __init__(self, bot: NetworkRelayBot) -> None:
        self._bot = bot

    def _render(self, name: str, **context: Any) -> discord.ui.View:
        from bot.app.widgets import render_view

        return cast("discord.ui.View", render_view(name, self._bot, **context))

    def register_join_network_view(self) -> discord.ui.View:
        view = self._render("join_network")
        self._bot.add_view(view)
        return view

    def register_network_admin_view(self) -> discord.ui.View:
        view = self._render("network_admin")
        self._bot.add_view(view)
        return view

    def register_moderator_review_view(self, request_id: int) -> discord.ui.View:
        view = self._render("moderator_review", request_id=request_id)
        self._bot.add_view(view)
        return view

    def register_client_profile_view(
        self,
        client_id: int,
        network_keys: list[str],
        *,
        subscribed_keys: set[str] | None = None,
        timecode_enabled: bool = False,
    ) -> discord.ui.View:
        view = self._render(
            "network_profile",
            client_id=client_id,
            network_keys=network_keys,
            subscribed_keys=subscribed_keys or set(),
            timecode_enabled=timecode_enabled,
        )
        self._bot.add_view(view)
        return view

    def register_subscribe_setup_view(
        self,
        subscription_id: int,
        network_key: str,
    ) -> discord.ui.View:
        view = self._render(
            "subscribe_setup",
            subscription_id=subscription_id,
            network_key=network_key,
        )
        self._bot.add_view(view)
        return view

    def register_subscription_moderation_view(
        self,
        subscription: ClientSubscription,
        network: Network,
        setup_state: SubscriptionSetupState,
    ) -> discord.ui.View:
        view = self._render(
            "subscription_moderation",
            subscription_id=subscription.id,
            network_key=network.key,
            show_subscribe_connected=not setup_state.subscribe_confirmed,
            show_blacklist=setup_state.fully_configured,
        )
        self._bot.add_view(view)
        return view

    def register_client_profile_for_client(
        self,
        client: Client,
        network_keys: list[str],
    ) -> discord.ui.View:
        return self.register_client_profile_view(
            client.id,
            network_keys,
            timecode_enabled=client.timecode_enabled,
        )
