"""Characterize pre-refactor repository boundaries and execution semantics."""

from __future__ import annotations

import inspect

import pytest
from store_helpers import (
    create_test_client,
    create_test_network,
    create_test_subscription,
)

from bot.db.connection import Database
from bot.db.store import ClientStore, NetworkStore


def test_client_repository_owns_subscription_and_blacklist_methods() -> None:
    """Track B split inventory — these methods move to dedicated repositories."""
    subscription_methods = {
        "create_subscription",
        "get_subscription_by_id",
        "get_subscription_by_client_and_key",
        "detach_subscriptions_from_network",
        "relink_subscription",
        "get_subscription",
        "get_subscription_by_publish_channel",
        "list_subscriptions_by_network",
        "list_subscriptions_by_client",
        "list_all_subscriptions",
        "update_moderation_message_id",
        "update_publish_setup_message_id",
        "update_subscribe_setup_message_id",
        "update_activation_welcome_message_id",
        "set_subscribe_confirmed",
        "set_subscription_enabled",
        "delete_subscription",
        "delete_subscriptions_by_network",
    }
    blacklist_methods = {
        "add_blacklist",
        "remove_blacklist",
        "is_blacklisted",
        "is_relay_blocked",
        "list_blacklisted_client_ids",
        "delete_blacklists_for_subscription",
        "delete_blacklists_for_client",
        "delete_blacklists_blocking_client",
    }

    client_methods = set(dir(ClientStore))
    assert subscription_methods.issubset(client_methods)
    assert blacklist_methods.issubset(client_methods)


def test_database_execute_commits_each_statement(tmp_path) -> None:
    """Current autocommit behavior — each execute() commits immediately."""
    source = inspect.getsource(Database.execute)
    assert "commit()" in source


@pytest.mark.asyncio
async def test_network_delete_leaves_detached_subscriptions_on_mid_failure(db) -> None:
    """Characterize non-atomic network deletion before transaction support."""
    network_repo = NetworkStore(db)
    client_repo = ClientStore(db)

    network = await create_test_network(network_repo, key="alpha", display_name="Alpha")
    client = await create_test_client(client_repo, guild_id=1, server_name="Acme")
    subscription = await create_test_subscription(
        client_repo,
        client=client,
        network=network,
    )

    await client_repo.detach_subscriptions_from_network(network.id, network.key)

    updated = await client_repo.get_subscription_by_id(subscription.id)
    assert updated is not None
    assert updated.network_id is None
    assert updated.network_key == "alpha"

    still_there = await network_repo.get_by_key("alpha")
    assert still_there is not None
