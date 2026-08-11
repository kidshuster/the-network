from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.app.layout.applier import ApplyMode, apply_layout
from bot.app.layout.compiler import DesiredResource, ResourceKind
from bot.app.layout.inventory import gather_guild_inventory
from bot.app.layout.loader import clear_layout_cache
from bot.app.layout.managed import hub_channel_aliases, hub_channel_name
from bot.app.layout.roles import LayoutContext
from bot.app.widgets.migration import MigrationReviewDecision
from bot.core.channels.migration import (
    DesiredMigrationResource,
    GuildInventory,
    InventoryChannel,
    StoredResourceRef,
    apply_manual_resolutions,
    build_migration_plan,
)
from bot.features.channels.resolve import HUB_CHANNEL_ADMIN
from bot.features.recipes.hub.migrate import HubMigrationResult, desired_hub_migration_resources


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    clear_layout_cache()
    yield
    clear_layout_cache()


def test_hub_channel_aliases_include_legacy_names() -> None:
    aliases = hub_channel_aliases(HUB_CHANNEL_ADMIN)
    assert aliases[0] == hub_channel_name(HUB_CHANNEL_ADMIN)
    assert "commands" in aliases
    assert "moderator-only" in aliases


def test_build_migration_plan_binds_managed_id() -> None:
    inventory = GuildInventory(
        channels=(
            InventoryChannel(11, "Moderation", "category"),
            InventoryChannel(21, "old-admin", "text", parent_id=11),
        )
    )
    desired = (
        DesiredMigrationResource("moderation", "category", "Moderation"),
        DesiredMigrationResource(
            "admin",
            "text",
            "admin",
            aliases=("commands",),
            category_key="moderation",
        ),
    )
    plan = build_migration_plan(
        inventory,
        desired,
        stored=(StoredResourceRef("admin", 21, "text"),),
    )
    assert plan.bound_ids()["admin"] == 21
    assert plan.bindings[0].source == "managed_id" or any(
        item.resource_key == "admin" and item.source == "managed_id" for item in plan.bindings
    )


def test_build_migration_plan_unique_legacy_alias() -> None:
    inventory = GuildInventory(
        channels=(InventoryChannel(21, "commands", "text"),)
    )
    desired = (
        DesiredMigrationResource(
            "admin",
            "text",
            "admin",
            aliases=("commands", "moderator-only"),
        ),
    )
    plan = build_migration_plan(inventory, desired)
    assert plan.bound_ids() == {"admin": 21}
    assert plan.delete_candidates == ()
    assert not plan.needs_review


def test_build_migration_plan_ambiguous_alias() -> None:
    inventory = GuildInventory(
        channels=(
            InventoryChannel(21, "commands", "text"),
            InventoryChannel(22, "moderator-only", "text"),
        )
    )
    desired = (
        DesiredMigrationResource(
            "admin",
            "text",
            "admin",
            aliases=("commands", "moderator-only"),
        ),
    )
    plan = build_migration_plan(inventory, desired)
    assert plan.bindings == ()
    assert len(plan.ambiguous) == 1
    assert plan.needs_review


def test_build_migration_plan_retired_delete_and_client_preserve() -> None:
    inventory = GuildInventory(
        channels=(
            InventoryChannel(21, "welcome-sink", "text"),
            InventoryChannel(31, "Client Cat", "category"),
            InventoryChannel(32, "client-profile", "text", parent_id=31),
            InventoryChannel(33, "commands", "text", parent_id=31),
        )
    )
    plan = build_migration_plan(
        inventory,
        (),
        retired_names=frozenset({"welcome-sink", "commands"}),
        client_discord_ids=frozenset({31, 32}),
        client_category_ids=frozenset({31}),
    )
    assert [item.discord_id for item in plan.delete_candidates] == [21]
    preserved_ids = {item.discord_id for item in plan.preserve_client}
    assert preserved_ids == {31, 32, 33}
    assert plan.needs_review


def test_apply_manual_resolutions_filters_deletes_and_binds() -> None:
    inventory = GuildInventory(
        channels=(
            InventoryChannel(21, "commands", "text"),
            InventoryChannel(22, "moderator-only", "text"),
            InventoryChannel(23, "welcome-sink", "text"),
        )
    )
    desired = (
        DesiredMigrationResource(
            "admin",
            "text",
            "admin",
            aliases=("commands", "moderator-only"),
        ),
    )
    plan = build_migration_plan(
        inventory,
        desired,
        retired_names=frozenset({"welcome-sink"}),
    )
    resolved = apply_manual_resolutions(
        plan,
        inventory=inventory,
        desired=desired,
        resolutions={"admin": 21},
        confirmed_delete_ids=frozenset({23}),
    )
    assert resolved.bound_ids() == {"admin": 21}
    assert resolved.ambiguous == ()
    assert [item.discord_id for item in resolved.delete_candidates] == [23]


def test_gather_guild_inventory_snapshots_text_and_categories() -> None:
    guild = MagicMock(spec=discord.Guild)
    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.name = "Moderation"
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 20
    channel.name = "admin"
    channel.category_id = 10
    channel.is_news = MagicMock(return_value=False)
    guild.categories = [category]
    guild.text_channels = [channel]
    guild.rules_channel = None
    guild.public_updates_channel = None

    inventory = gather_guild_inventory(guild)
    assert {item.discord_id for item in inventory.channels} == {10, 20}


@pytest.mark.asyncio
async def test_apply_layout_prefers_bound_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    guild = MagicMock(spec=discord.Guild)
    bound = MagicMock(spec=discord.CategoryChannel)
    bound.id = 99
    bound.name = "Old Name"
    bound.position = 0
    bound.overwrites = {}
    guild.get_channel = MagicMock(return_value=bound)
    guild.categories = [bound]
    guild.text_channels = []
    guild.channels = [bound]
    guild.rules_channel = None
    guild.public_updates_channel = None

    bot_member = MagicMock(spec=discord.Member)
    access = MagicMock(spec=discord.Role)
    context = LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access,
        reason="test",
    )
    ensure = AsyncMock(
        return_value=MagicMock(
            resource=bound,
            sync=MagicMock(success=True, changed=False, failures=[]),
        )
    )
    monkeypatch.setattr(
        "bot.app.layout.applier.permission_service.ensure_category",
        ensure,
    )

    batch = await apply_layout(
        context,
        [
            DesiredResource(
                id="moderation",
                kind=ResourceKind.CATEGORY,
                name="Moderation",
            )
        ],
        mode=ApplyMode.ENSURE,
        bound_ids={"moderation": 99},
    )
    assert batch.success
    assert batch.resource("moderation") is bound
    ensure.assert_awaited()
    assert ensure.await_args.kwargs["existing"] is bound


@pytest.mark.asyncio
async def test_migrate_hub_layout_skips_review_on_clean_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bot.features.recipes.hub import migrate as migrate_mod

    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    guild.categories = []
    guild.text_channels = []
    guild.rules_channel = None
    guild.public_updates_channel = None
    layout_context = MagicMock(spec=LayoutContext)
    layout_context.guild = guild
    layout_context.reason = "test"

    monkeypatch.setattr(
        migrate_mod,
        "build_migration_plan",
        MagicMock(
            return_value=build_migration_plan(
                GuildInventory(channels=()),
                desired_hub_migration_resources()[:1],
            )
        ),
    )
    apply_bindings = AsyncMock(return_value=["ok"])
    monkeypatch.setattr(migrate_mod, "apply_migration_bindings", apply_bindings)
    persist = AsyncMock()
    monkeypatch.setattr(migrate_mod, "_persist_hub_bindings", persist)

    result = await migrate_mod.migrate_hub_layout(
        guild,
        layout_context,
        context=None,
        clients=[],
        interaction=None,
    )
    assert isinstance(result, HubMigrationResult)
    assert result.success is True
    apply_bindings.assert_awaited()
    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_migrate_hub_layout_requires_review_without_interaction() -> None:
    from bot.features.recipes.hub import migrate as migrate_mod

    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 21
    channel.name = "welcome-sink"
    channel.category_id = None
    channel.is_news = MagicMock(return_value=False)
    guild.categories = []
    guild.text_channels = [channel]
    guild.rules_channel = None
    guild.public_updates_channel = None
    layout_context = MagicMock(spec=LayoutContext)
    layout_context.guild = guild

    result = await migrate_mod.migrate_hub_layout(
        guild,
        layout_context,
        context=None,
        interaction=None,
    )
    assert result.success is False
    assert result.plan.needs_review
    assert result.reason is not None


@pytest.mark.asyncio
async def test_migrate_hub_layout_uses_review_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bot.features.recipes.hub import migrate as migrate_mod

    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 21
    channel.name = "welcome-sink"
    channel.category_id = None
    channel.is_news = MagicMock(return_value=False)
    guild.categories = []
    guild.text_channels = [channel]
    guild.get_channel = MagicMock(return_value=channel)
    guild.rules_channel = None
    guild.public_updates_channel = None
    layout_context = MagicMock(spec=LayoutContext)
    layout_context.guild = guild
    layout_context.reason = "test"
    interaction = MagicMock(spec=discord.Interaction)

    monkeypatch.setattr(
        "bot.app.widgets.migration.present_migration_review",
        AsyncMock(
            return_value=MigrationReviewDecision(resolutions={}, confirm_deletes=True)
        ),
    )
    delete = AsyncMock(return_value=True)
    monkeypatch.setattr("bot.app.layout.bindings.delete_channel", delete)

    result = await migrate_mod.migrate_hub_layout(
        guild,
        layout_context,
        context=None,
        interaction=interaction,
    )
    assert result.success is True
    delete.assert_awaited()
