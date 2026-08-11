from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.app.features import build_recipe_registry
from bot.app.recipes import RecipeRegistryError


def _bot(*, core: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        bot_context=core,
        settings=SimpleNamespace(
            guild_id=100,
            network_access_role_name="The Network",
            network_operator_role_name="Network Operator",
        ),
    )


def test_catalog_exposes_stable_public_operations() -> None:
    registry = build_recipe_registry(_bot())

    expected = {
        "blacklist.replace",
        "client.delete",
        "client.edit_profile",
        "client.provision_from_request",
        "client.toggle_timecode",
        "clients.reconnect",
        "clients.rectify",
        "hub.ensure_installs",
        "hub.handle_announcement",
        "hub.initialize",
        "hub.migrate",
        "hub.reset_data",
        "hub.teardown_installs",
        "hub.uninitialize",
        "network.create",
        "network.delete",
        "relay.deliver",
        "relay.on_message",
        "request.approve",
        "request.deny",
        "request.submit",
        "server.init",
        "server.sync_join_guide",
        "server.uninit",
        "subscription.confirm_connected",
        "subscription.create",
        "subscription.leave",
        "subscription.webhook_updated",
        "text.parse_dates",
    }
    assert {registry.spec(name).name for name in expected} == expected


def test_entry_surfaces_are_owned_by_trigger_catalog() -> None:
    from bot.app.triggers import build_trigger_catalog
    from bot.core.triggers import TriggerKind

    catalog = build_trigger_catalog()
    registry = build_recipe_registry(_bot())
    commands = {
        (spec.slash_group, spec.slash_name): spec
        for spec in catalog.list_by_kind(TriggerKind.SLASH)
    }

    assert set(commands) == {
        ("server", "init"),
        ("server", "probe"),
        ("server", "sync-join-guide"),
        ("server", "uninit"),
    }
    for spec in commands.values():
        assert spec.default_permissions == ("manage_guild",)
        assert spec.presenter is not None
        assert registry.spec(spec.presenter).name == spec.presenter
        assert registry.spec(spec.recipe).name == spec.recipe

    assert {s.recipe for s in catalog.triggers_for_event("app.services")} == {
        "app.initialize_relay"
    }
    assert {s.recipe for s in catalog.triggers_for_event("app.setup")} == {
        "app.register_persistent_views",
        "app.validate_features",
    }
    assert {s.recipe for s in catalog.triggers_for_event("app.ready")} == {
        "app.sync_changelog",
        "app.sync_subscription_stickies",
    }
    assert {s.recipe for s in catalog.triggers_for_event("discord.message")} == {
        "relay.on_message"
    }
    assert {s.recipe for s in catalog.triggers_for_event("discord.webhooks_update")} == {
        "subscription.webhook_updated"
    }


async def test_message_event_composes_announcement_and_relay_recipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bot.app.triggers import build_trigger_catalog, dispatch_event

    relay = MagicMock()
    relay.is_potential_feed_message.return_value = True
    relay.relay_message = AsyncMock(return_value="relayed")
    relay.feed_reject_reason.return_value = None
    core = SimpleNamespace(relay_service=relay)
    bot = _bot(core=core)
    handled = AsyncMock()
    monkeypatch.setattr(
        "bot.features.recipes.hub.announcements.handle_network_announcements_message",
        handled,
    )
    registry = build_recipe_registry(bot)
    message = MagicMock(spec=discord.Message)

    assert await dispatch_event(
        build_trigger_catalog(),
        registry.run,
        "discord.message",
        message=message,
    ) == ["relayed"]
    handled.assert_awaited_once_with(bot, message)
    relay.relay_message.assert_awaited_once_with(message)


async def test_relay_recipe_ignores_non_feed_messages() -> None:
    relay = MagicMock()
    relay.is_potential_feed_message.return_value = False
    relay.relay_message = AsyncMock()
    registry = build_recipe_registry(_bot(core=SimpleNamespace(relay_service=relay)))

    result = await registry.run("relay.deliver", message=MagicMock(spec=discord.Message))

    assert result is None
    relay.relay_message.assert_not_awaited()


async def test_webhook_event_ignores_non_text_channels() -> None:
    from bot.app.triggers import build_trigger_catalog, dispatch_event

    registry = build_recipe_registry(_bot(core=SimpleNamespace()))
    channel = MagicMock(spec=discord.CategoryChannel)

    assert await dispatch_event(
        build_trigger_catalog(),
        registry.run,
        "discord.webhooks_update",
        channel=channel,
    ) == [None]


async def test_date_parser_is_available_through_recipe_boundary() -> None:
    registry = build_recipe_registry(_bot())

    assert await registry.run("text.parse_dates", text="No dates here") == "No dates here"


async def test_blacklist_recipe_reconciles_only_allowed_clients() -> None:
    repo = MagicMock()
    repo.get_subscription_by_id = AsyncMock(return_value=SimpleNamespace(client_id=1, network_id=9))
    repo.list_subscriptions_by_network = AsyncMock(
        return_value=[
            SimpleNamespace(client_id=1),
            SimpleNamespace(client_id=2),
            SimpleNamespace(client_id=3),
        ]
    )
    repo.list_blacklisted_client_ids = AsyncMock(return_value=[2])
    repo.add_blacklist = AsyncMock()
    repo.remove_blacklist = AsyncMock()
    core = SimpleNamespace(store=SimpleNamespace(clients=repo))
    registry = build_recipe_registry(_bot(core=core))

    count = await registry.run(
        "blacklist.replace",
        subscription_id=4,
        selected_client_ids=["3", "999"],
    )

    assert count == 1
    repo.add_blacklist.assert_awaited_once_with(4, 3)
    repo.remove_blacklist.assert_awaited_once_with(4, 2)


async def test_blacklist_recipe_hides_missing_record_handling() -> None:
    repo = MagicMock()
    repo.get_subscription_by_id = AsyncMock(return_value=None)
    core = SimpleNamespace(store=SimpleNamespace(clients=repo))
    registry = build_recipe_registry(_bot(core=core))

    with pytest.raises(RecipeRegistryError, match="blacklist.replace") as raised:
        await registry.run(
            "blacklist.replace",
            subscription_id=4,
            selected_client_ids=[],
        )
    assert isinstance(raised.value.__cause__, ValueError)
    assert str(raised.value.__cause__) == "Subscription was not found."


async def test_command_recipe_rejects_wrong_guild_at_boundary() -> None:
    registry = build_recipe_registry(_bot(core=SimpleNamespace()))
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 999

    with pytest.raises(RecipeRegistryError, match="server.init") as raised:
        await registry.run("server.init", interaction=interaction)
    assert raised.value.__cause__ is not None
    assert "configured hub guild" in str(raised.value.__cause__)


async def test_network_create_recipe_owns_complete_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network = SimpleNamespace(id=9, key="alpha")
    networks = MagicMock()
    networks.get_by_key = AsyncMock(return_value=None)
    networks.create = AsyncMock(return_value=network)
    core = SimpleNamespace(
        store=SimpleNamespace(networks=networks),
        refresh_network_counts=AsyncMock(),
    )
    bot = _bot(core=core)
    resync = AsyncMock(return_value=3)
    refresh_profiles = AsyncMock(return_value=2)
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resync_subscriptions_for_network",
        resync,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.profile_sync.refresh_all_client_profiles",
        refresh_profiles,
    )
    registry = build_recipe_registry(bot)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    views = MagicMock()

    result = await registry.run(
        "network.create",
        guild=guild,
        key="alpha",
        display_name="Alpha",
        view_registry=views,
    )

    assert result == (network, 2, 3)
    networks.create.assert_awaited_once_with(guild_id=100, key="alpha", display_name="Alpha")
    core.refresh_network_counts.assert_awaited_once()
    resync.assert_awaited_once()
    refresh_profiles.assert_awaited_once()


async def test_network_create_recipe_stops_before_mutation_for_duplicate() -> None:
    existing = SimpleNamespace(key="alpha")
    networks = MagicMock()
    networks.get_by_key = AsyncMock(return_value=existing)
    networks.create = AsyncMock()
    core = SimpleNamespace(store=SimpleNamespace(networks=networks))
    registry = build_recipe_registry(_bot(core=core))

    with pytest.raises(RecipeRegistryError, match="network.create") as raised:
        await registry.run(
            "network.create",
            guild=MagicMock(spec=discord.Guild),
            key="alpha",
            display_name="Alpha",
            view_registry=MagicMock(),
        )
    networks.create.assert_not_awaited()
    assert raised.value.__cause__ is not None
    assert "already exists" in str(raised.value.__cause__)


async def test_network_delete_recipe_refreshes_state_and_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network = SimpleNamespace(key="alpha")
    networks = MagicMock()
    networks.get_by_key = AsyncMock(return_value=network)
    networks.delete_with_relations = AsyncMock()
    core = SimpleNamespace(
        store=SimpleNamespace(networks=networks),
        refresh_projections=AsyncMock(),
    )
    refresh_profiles = AsyncMock(return_value=2)
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.profile_sync.refresh_all_client_profiles",
        refresh_profiles,
    )
    registry = build_recipe_registry(_bot(core=core))
    guild = MagicMock(spec=discord.Guild)

    result = await registry.run(
        "network.delete",
        guild=guild,
        key="alpha",
        view_registry=MagicMock(),
    )

    assert result is network
    networks.delete_with_relations.assert_awaited_once_with("alpha")
    core.refresh_projections.assert_awaited_once()
    refresh_profiles.assert_awaited_once()
