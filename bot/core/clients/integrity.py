from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import discord

from bot.core.clients.resources import (
    fetch_client_role,
    fetch_publish_channel,
    fetch_subscribe_channel,
    resolve_client_category,
    resolve_client_profile_channel,
)
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription

ClientIntegrityState = Literal["healthy", "partial", "irrecoverable"]


@dataclass(frozen=True)
class ClientIntegrity:
    """Discord-side integrity for a registered client row.

    Repository getters stay pure; callers supply the client (and optional
    subscriptions) and this helper only inspects Discord objects.
    """

    role_present: bool
    category_present: bool
    profile_channel_present: bool
    broken_subscription_ids: tuple[int, ...] = ()

    @property
    def is_healthy(self) -> bool:
        return self.state == "healthy"

    @property
    def state(self) -> ClientIntegrityState:
        """Classify Discord resource completeness for lifecycle decisions.

        Ordinary reconciliation never deletes a client. Partial clients are
        repaired through the pending-approval flow; ``irrecoverable`` is reserved
        for rows that cannot safely be repaired in place (not currently emitted).
        """
        if (
            self.role_present
            and self.category_present
            and self.profile_channel_present
            and not self.broken_subscription_ids
        ):
            return "healthy"
        return "partial"


async def inspect_client_integrity(
    guild: discord.Guild,
    client: Client,
    subscriptions: Sequence[ClientSubscription] = (),
) -> ClientIntegrity:
    role = await fetch_client_role(guild, client)
    category = await resolve_client_category(guild, client)
    profile = await resolve_client_profile_channel(guild, client)

    broken: list[int] = []
    for subscription in subscriptions:
        publish = await fetch_publish_channel(guild, subscription)
        subscribe = await fetch_subscribe_channel(guild, subscription)
        if publish is None or subscribe is None:
            broken.append(subscription.id)

    return ClientIntegrity(
        role_present=role is not None,
        category_present=category is not None,
        profile_channel_present=profile is not None,
        broken_subscription_ids=tuple(broken),
    )
