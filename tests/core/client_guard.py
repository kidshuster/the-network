from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from tests.core.resource_guard import is_smoke_client_server_name

if TYPE_CHECKING:
    from bot.app.context import BotContext


@dataclass(frozen=True)
class ProtectedClient:
    id: int
    server_name: str
    role_id: int
    category_id: int
    profile_channel_id: int
    subscriptions: tuple[ProtectedSubscription, ...]


@dataclass(frozen=True)
class ProtectedSubscription:
    network_key: str
    publish_channel_id: int | None
    subscribe_channel_id: int


async def snapshot_protected_clients(
    context: BotContext,
    guild_id: int,
) -> tuple[ProtectedClient, ...]:
    """Capture non-smoke clients that no live test is authorized to delete."""
    protected: list[ProtectedClient] = []
    for client in await context.store.clients.list_all():
        if client.guild_id != guild_id or is_smoke_client_server_name(client.server_name):
            continue
        subscriptions = tuple(
            ProtectedSubscription(
                network_key=subscription.network_key,
                publish_channel_id=subscription.publish_channel_id,
                subscribe_channel_id=subscription.subscribe_channel_id,
            )
            for subscription in await context.store.clients.list_subscriptions_by_client(
                client.id
            )
        )
        protected.append(
            ProtectedClient(
                id=client.id,
                server_name=client.server_name,
                role_id=client.client_role_id,
                category_id=client.category_id,
                profile_channel_id=client.profile_channel_id,
                subscriptions=subscriptions,
            )
        )
    return tuple(protected)


async def assert_protected_clients_unchanged(
    guild: discord.Guild,
    context: BotContext,
    snapshot: tuple[ProtectedClient, ...],
    *,
    phase: str,
) -> None:
    """Fail immediately if any production client record or Discord resource disappeared."""
    failures: list[str] = []
    for expected in snapshot:
        current = await context.store.clients.get_by_id(expected.id)
        if current is None:
            failures.append(f"{expected.server_name}: database record deleted")
            continue
        if current.client_role_id != expected.role_id or guild.get_role(expected.role_id) is None:
            failures.append(f"{expected.server_name}: client role deleted or replaced")
        category = guild.get_channel(expected.category_id)
        if not isinstance(category, discord.CategoryChannel):
            failures.append(f"{expected.server_name}: client category deleted or replaced")
        profile = guild.get_channel(expected.profile_channel_id)
        if not isinstance(profile, discord.TextChannel):
            failures.append(f"{expected.server_name}: profile channel deleted or replaced")
        current_subscriptions = await context.store.clients.list_subscriptions_by_client(
            expected.id
        )
        for expected_subscription in expected.subscriptions:
            subscription = next(
                (
                    item
                    for item in current_subscriptions
                    if item.network_key == expected_subscription.network_key
                    and item.publish_channel_id == expected_subscription.publish_channel_id
                    and item.subscribe_channel_id == expected_subscription.subscribe_channel_id
                ),
                None,
            )
            if subscription is None:
                failures.append(
                    f"{expected.server_name}: subscription {expected_subscription.network_key} "
                    "deleted or replaced"
                )
                continue
            for label, channel_id in (
                ("publish", expected_subscription.publish_channel_id),
                ("subscribe", expected_subscription.subscribe_channel_id),
            ):
                if channel_id is None:
                    continue
                channel = guild.get_channel(channel_id)
                if not isinstance(channel, discord.TextChannel):
                    failures.append(
                        f"{expected.server_name}: {label} channel {channel_id} deleted"
                    )
    if failures:
        raise RuntimeError(
            f"Protected-client invariant failed after {phase}: " + "; ".join(failures)
        )
