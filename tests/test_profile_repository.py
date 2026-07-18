from __future__ import annotations

import pytest

from bot.db.repositories import NetworkRepository, ProfileRepository
from bot.domain.errors import ProfileValidationError


@pytest.mark.asyncio
async def test_profile_upsert_and_get(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    profile = await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=1001,
        profile_starter_message_id=1001,
        source_channel_id=201,
        network_id=network.id,
        server_name="Test Server",
        display_name="Test Server",
        enabled=True,
    )
    assert profile.server_name == "Test Server"
    assert profile.source_channel_id == 201

    fetched = await profile_repo.get_by_thread_id(1001)
    assert fetched == profile
    by_source = await profile_repo.get_by_source_channel(201)
    assert by_source == profile


@pytest.mark.asyncio
async def test_profile_rejects_duplicate_source_channel(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="alpha",
        display_name="Alpha",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=1001,
        profile_starter_message_id=1001,
        source_channel_id=201,
        network_id=network.id,
        server_name="One",
        display_name="One",
        enabled=True,
    )
    with pytest.raises(ProfileValidationError, match="already used"):
        await profile_repo.upsert(
            guild_id=100,
            profile_thread_id=1002,
            profile_starter_message_id=1002,
            source_channel_id=201,
            network_id=network.id,
            server_name="Two",
            display_name="Two",
            enabled=True,
        )


@pytest.mark.asyncio
async def test_profile_set_enabled(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="beta",
        display_name="Beta",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=1001,
        profile_starter_message_id=1001,
        source_channel_id=201,
        network_id=network.id,
        server_name="Server",
        display_name="Server",
        enabled=True,
    )
    disabled = await profile_repo.set_enabled_by_thread(1001, False)
    assert disabled.enabled is False


@pytest.mark.asyncio
async def test_profile_lookup_by_network_and_server_name(db) -> None:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="gamma",
        display_name="Gamma",
        feed_category_id=200,
        output_channel_id=300,
        concat_channel_id=None,
    )
    await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=1001,
        profile_starter_message_id=1001,
        source_channel_id=201,
        network_id=network.id,
        server_name="Partner One",
        display_name="Partner One",
        enabled=True,
    )

    fetched = await profile_repo.get_by_network_and_server_name(network.id, "partner one")
    assert fetched is not None
    assert fetched.server_name == "Partner One"

    by_network = await profile_repo.list_by_network_id(network.id)
    assert len(by_network) == 1

    toggled = await profile_repo.set_enabled_by_network_and_server_name(
        network.id,
        "Partner One",
        False,
    )
    assert toggled.enabled is False
