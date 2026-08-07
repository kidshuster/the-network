from __future__ import annotations

import inspect


def test_client_approval_grants_leaders_channel_access() -> None:
    """New clients created via join-request approval should sync Leaders access immediately."""
    from bot.services.server_request_service import ServerRequestService

    source = inspect.getsource(ServerRequestService.approve_request)
    assert "grant_leaders_channel_access" in source


def test_guild_init_syncs_leaders_for_all_client_roles() -> None:
    """Server init re-syncs Leaders permissions for every stored client role."""
    from bot.services.guild_init import initialize_guild

    source = inspect.getsource(initialize_guild)
    assert "ensure_leaders_channel" in source
