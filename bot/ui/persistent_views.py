from __future__ import annotations

from typing import TYPE_CHECKING

from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.network import Network
from bot.core.stickies.subscription_setup import SubscriptionSetupState

if TYPE_CHECKING:
    import discord

    from bot.client import NetworkRelayBot


class PersistentViewRegistry:
    """Build and register persistent views for hub stickies and client profiles."""

    def __init__(self, bot: NetworkRelayBot) -> None:
        self._bot = bot

    def register_join_network_view(self) -> discord.ui.View:
        from bot.ui.join_views import JoinNetworkView

        view = JoinNetworkView(self._bot)
        self._bot.add_view(view)
        return view

    def register_network_admin_view(self) -> discord.ui.View:
        from bot.ui.network_admin_views import NetworkAdminView

        view = NetworkAdminView(self._bot)
        self._bot.add_view(view)
        return view

    def register_moderator_review_view(self, request_id: int) -> discord.ui.View:
        from bot.ui.join_views import ModeratorReviewView

        view = ModeratorReviewView(self._bot, request_id)
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
        from bot.ui.network_views import NetworkProfileView

        view = NetworkProfileView(
            self._bot,
            client_id,
            network_keys,
            subscribed_keys=subscribed_keys,
            timecode_enabled=timecode_enabled,
        )
        self._bot.add_view(view)
        return view

    def register_subscribe_setup_view(
        self,
        subscription_id: int,
        network_key: str,
    ) -> discord.ui.View:
        from bot.ui.network_views import SubscribeSetupView

        view = SubscribeSetupView(self._bot, subscription_id, network_key)
        self._bot.add_view(view)
        return view

    def register_subscription_moderation_view(
        self,
        subscription: ClientSubscription,
        network: Network,
        setup_state: SubscriptionSetupState,
    ) -> discord.ui.View:
        from bot.ui.network_views import SubscriptionModerationView

        view = SubscriptionModerationView(
            self._bot,
            subscription.id,
            network.key,
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
