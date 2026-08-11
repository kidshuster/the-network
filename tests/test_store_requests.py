from __future__ import annotations

import pytest
from store_helpers import create_test_network

from bot.db.store import NetworkStore, RequestStore
from bot.domain.server_request import ServerRequestStatus


@pytest.mark.asyncio
async def test_create_and_get_by_id(db) -> None:
    repo = RequestStore(db)
    request = await repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=555,
        server_name=" Acme ",
        display_name=" Acme Display ",
        profile_image_url=" https://cdn.example/p.png ",
        profile_image_data=b"png",
    )
    assert request.server_name == "Acme"
    assert request.display_name == "Acme Display"
    assert request.profile_image_url == "https://cdn.example/p.png"
    assert request.status == ServerRequestStatus.PENDING

    fetched = await repo.get_by_id(request.id)
    assert fetched == request


@pytest.mark.asyncio
async def test_list_pending_and_get_pending_for_requester(db) -> None:
    repo = RequestStore(db)
    await repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=555,
        server_name="First",
        display_name="First",
        profile_image_url="https://cdn.example/1.png",
    )
    second = await repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=666,
        server_name="Second",
        display_name="Second",
        profile_image_url="https://cdn.example/2.png",
    )
    pending = await repo.list_pending()
    assert len(pending) == 2
    assert pending[0].id < pending[1].id

    for_requester = await repo.get_pending_for_requester(666)
    assert for_requester == second


@pytest.mark.asyncio
async def test_get_pending_for_requester_with_network_id(db) -> None:
    network_repo = NetworkStore(db)
    network = await create_test_network(network_repo)
    repo = RequestStore(db)
    request = await repo.create(
        guild_id=100,
        network_id=network.id,
        requester_user_id=555,
        server_name="Networked",
        display_name="Networked",
        profile_image_url="https://cdn.example/n.png",
    )
    fetched = await repo.get_pending_for_requester(555, network_id=network.id)
    assert fetched == request


@pytest.mark.asyncio
async def test_set_moderator_message_id_and_resolve(db) -> None:
    repo = RequestStore(db)
    request = await repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=555,
        server_name="Acme",
        display_name="Acme",
        profile_image_url="https://cdn.example/p.png",
    )
    with_message = await repo.set_moderator_message_id(request.id, 900)
    assert with_message.moderator_message_id == 900

    approved = await repo.resolve(
        request.id,
        status=ServerRequestStatus.APPROVED,
        resolved_by_user_id=777,
    )
    assert approved.status == ServerRequestStatus.APPROVED
    assert approved.resolved_by_user_id == 777


@pytest.mark.asyncio
async def test_list_by_server_name_prefix_and_delete(db) -> None:
    repo = RequestStore(db)
    await repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=555,
        server_name="Smoke Accept Test",
        display_name="Smoke Accept Test",
        profile_image_url="https://cdn.example/p.png",
    )
    await repo.create(
        guild_id=100,
        network_id=None,
        requester_user_id=556,
        server_name="Smoke Deny Test",
        display_name="Smoke Deny Test",
        profile_image_url="https://cdn.example/p2.png",
    )
    accept_matches = await repo.list_by_server_name_prefix("Smoke Accept")
    assert len(accept_matches) == 1
    assert accept_matches[0].server_name == "Smoke Accept Test"

    request = accept_matches[0]
    await repo.delete_by_id(request.id)
    assert await repo.get_by_id(request.id) is None
