from __future__ import annotations

from typing import Protocol

import discord

from bot.core.clients.setup_state import SubscriptionSetupState
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.network import Network


class ViewRegistry(Protocol):
    """Core contract implemented by the Discord presentation layer."""

    def register_join_network_view(self) -> discord.ui.View: ...

    def register_network_admin_view(self) -> discord.ui.View: ...

    def register_moderator_review_view(self, request_id: int) -> discord.ui.View: ...

    def register_client_profile_view(
        self,
        client_id: int,
        network_keys: list[str],
        *,
        subscribed_keys: set[str] | None = None,
        timecode_enabled: bool = False,
    ) -> discord.ui.View: ...

    def register_subscribe_setup_view(
        self,
        subscription_id: int,
        network_key: str,
    ) -> discord.ui.View: ...

    def register_subscription_moderation_view(
        self,
        subscription: ClientSubscription,
        network: Network,
        setup_state: SubscriptionSetupState,
    ) -> discord.ui.View: ...

    def register_client_profile_for_client(
        self,
        client: Client,
        network_keys: list[str],
    ) -> discord.ui.View: ...
