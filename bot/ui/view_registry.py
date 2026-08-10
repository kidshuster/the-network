from __future__ import annotations

from typing import Protocol

import discord

from bot.domain.client import Client
from bot.domain.client_subscription import ClientSubscription
from bot.domain.network import Network
from bot.stickies.subscription_setup import SubscriptionSetupState


class ViewRegistry(Protocol):
    """Narrow protocol for registering persistent Discord UI views without importing bot.ui."""

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
