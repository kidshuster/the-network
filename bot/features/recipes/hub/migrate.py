from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import discord

from bot.contracts.recipes import recipe
from bot.core.channels.migration import (
    DesiredMigrationResource,
    MigrationPlan,
    ResourceKindName,
    StoredResourceRef,
    apply_manual_resolutions,
    build_migration_plan,
)
from bot.core.database.store import ManagedResource
from bot.core.models.client import Client
from bot.features.channels.layout import (
    LayoutContext,
    apply_migration_bindings,
    gather_guild_inventory,
)
from bot.features.channels.layout.loader import load_layout
from bot.features.recipes.hub.leaders import (
    CHANGELOG_CHANNEL_SETTINGS_KEY,
    LEADERS_CHANNEL_SETTINGS_KEY,
)

if TYPE_CHECKING:
    from bot.contracts.recipes import RecipeContext

logger = logging.getLogger(__name__)


@dataclass
class HubMigrationResult:
    success: bool
    plan: MigrationPlan
    bound_ids: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    reason: str | None = None


def desired_hub_migration_resources() -> tuple[DesiredMigrationResource, ...]:
    layout = load_layout().layout
    resources: list[DesiredMigrationResource] = []
    for category_key, category in layout.categories.items():
        resources.append(
            DesiredMigrationResource(
                resource_key=category_key,
                kind="category",
                name=category.name,
                aliases=tuple(category.legacy_names),
            )
        )
        for channel_key, channel in category.channels.items():
            kind: ResourceKindName = (
                "announcement" if channel.type == "announcement" else "text"
            )
            resources.append(
                DesiredMigrationResource(
                    resource_key=channel_key,
                    kind=kind,
                    name=channel.name,
                    aliases=tuple(channel.legacy_names),
                    category_key=category_key,
                    community_slot=channel.community_slot,
                )
            )
    return tuple(resources)


def _client_resource_ids(
    clients: list[Client],
    *,
    guild_id: int,
) -> tuple[frozenset[int], frozenset[int]]:
    category_ids: set[int] = set()
    discord_ids: set[int] = set()
    for client in clients:
        if client.guild_id != guild_id:
            continue
        category_ids.add(client.category_id)
        discord_ids.add(client.category_id)
        discord_ids.add(client.profile_channel_id)
    return frozenset(discord_ids), frozenset(category_ids)


async def _subscription_channel_ids(context: Any, client_ids: set[int]) -> frozenset[int]:
    ids: set[int] = set()
    for client_id in client_ids:
        listed = context.store.clients.list_subscriptions_by_client(client_id)
        subscriptions = await listed if inspect.isawaitable(listed) else listed
        for subscription in subscriptions or ():
            ids.add(subscription.publish_channel_id)
            ids.add(subscription.subscribe_channel_id)
    return frozenset(ids)


@recipe("hub.migrate")
async def migrate_hub_layout_recipe(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    layout_context: LayoutContext,
    interaction: discord.Interaction | None = None,
    clients: list[Client] | None = None,
) -> HubMigrationResult:
    return await migrate_hub_layout(
        guild,
        layout_context,
        context=recipe_context.core,
        bot=recipe_context.bot,
        clients=clients,
        interaction=interaction,
    )


async def migrate_hub_layout(
    guild: discord.Guild,
    layout_context: LayoutContext,
    *,
    context: Any | None,
    bot: Any | None = None,
    clients: list[Client] | None = None,
    interaction: discord.Interaction | None = None,
) -> HubMigrationResult:
    """Gather → match → optional review → bind/delete → persist hub resource IDs."""
    desired = desired_hub_migration_resources()
    inventory = gather_guild_inventory(guild)
    guild_clients = [client for client in (clients or []) if client.guild_id == guild.id]
    client_ids, client_category_ids = _client_resource_ids(guild_clients, guild_id=guild.id)
    if context is not None and guild_clients:
        client_ids |= await _subscription_channel_ids(
            context,
            {client.id for client in guild_clients},
        )

    stored: list[StoredResourceRef] = []
    if context is not None:
        listed = context.store.resources.list_for_guild(guild.id)
        resources = await listed if inspect.isawaitable(listed) else listed
        for resource in resources or ():
            if resource.owner_type not in (None, "hub"):
                continue
            stored.append(
                StoredResourceRef(
                    resource_key=resource.resource_key,
                    discord_id=resource.discord_id,
                    discord_type=resource.discord_type,
                )
            )

    layout = load_layout()
    plan = build_migration_plan(
        inventory,
        desired,
        stored=tuple(stored),
        retired_names=frozenset(layout.retired_channels),
        client_discord_ids=client_ids,
        client_category_ids=client_category_ids,
    )

    if plan.needs_review:
        if interaction is None:
            return HubMigrationResult(
                success=False,
                plan=plan,
                reason=(
                    "Hub migration needs operator review (ambiguous maps or obsolete "
                    "channel deletes), but no interaction is available."
                ),
            )

        presenter = bot if bot is not None else getattr(interaction, "client", None)
        if presenter is None or not hasattr(presenter, "present_migration_review"):
            return HubMigrationResult(
                success=False,
                plan=plan,
                reason="Hub migration review is unavailable in this runtime.",
            )
        from bot.errors import UserFacingError

        try:
            reviewed = await presenter.present_migration_review(interaction, plan)
        except UserFacingError as exc:
            return HubMigrationResult(
                success=False,
                plan=plan,
                reason=exc.message,
            )
        if reviewed is None:
            return HubMigrationResult(
                success=False,
                plan=plan,
                reason="Hub migration cancelled or timed out during review.",
            )
        plan = apply_manual_resolutions(
            plan,
            inventory=inventory,
            desired=desired,
            resolutions=reviewed.resolutions,
            confirmed_delete_ids=frozenset(
                item.discord_id for item in plan.delete_candidates
            )
            if reviewed.confirm_deletes
            else frozenset(),
        )
        if plan.ambiguous:
            return HubMigrationResult(
                success=False,
                plan=plan,
                reason="Hub migration still has unresolved ambiguous channel maps.",
            )

    notes = await apply_migration_bindings(layout_context, plan)
    bound_ids = plan.bound_ids()
    if context is not None:
        await _persist_hub_bindings(context, guild.id, plan)

    for item in plan.preserve_client:
        notes.append(f"Preserved client resource `#{item.name}`.")
    if plan.bindings or plan.delete_candidates:
        notes.append(
            f"Migration bound {len(plan.bindings)} resource(s); "
            f"removed {len(plan.delete_candidates)} obsolete channel(s)."
        )
    return HubMigrationResult(
        success=True,
        plan=plan,
        bound_ids=bound_ids,
        notes=notes,
    )


async def _await_maybe(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


async def _persist_hub_bindings(
    context: Any,
    guild_id: int,
    plan: MigrationPlan,
) -> None:
    desired = {item.resource_key: item for item in desired_hub_migration_resources()}
    for binding in plan.bindings:
        resource = desired.get(binding.resource_key)
        if resource is not None and resource.kind == "category":
            discord_type = "category"
        else:
            discord_type = "text"
        await _await_maybe(
            context.store.resources.upsert(
                ManagedResource(
                    guild_id=guild_id,
                    resource_key=binding.resource_key,
                    discord_type=discord_type,
                    discord_id=binding.discord_id,
                    owner_type="hub",
                    owner_id=guild_id,
                )
            )
        )
    leaders_id = plan.bound_ids().get("leaders_channel")
    changelog_id = plan.bound_ids().get("changelog")
    if leaders_id is not None:
        await _await_maybe(
            context.store.settings.set(LEADERS_CHANNEL_SETTINGS_KEY, str(leaders_id))
        )
    if changelog_id is not None:
        await _await_maybe(
            context.store.settings.set(CHANGELOG_CHANNEL_SETTINGS_KEY, str(changelog_id))
        )
