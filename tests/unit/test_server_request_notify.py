from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from view_registry_helpers import make_test_view_registry

from bot.core.database.store import RequestStore
from bot.features.recipes.hub.onboarding.service import ServerRequestService


@pytest.mark.asyncio
async def test_submit_request_defaults_display_name_to_server_name(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = MagicMock()
    context.store.requests = RequestStore(db)
    context.store.clients = MagicMock()
    context.store.clients.get_by_server_name = AsyncMock(return_value=None)

    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.add_view = MagicMock()

    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    guild.me = MagicMock()

    requester = MagicMock()
    requester.id = 1

    profile_image = MagicMock(spec=discord.Attachment)
    profile_image.url = "https://example.com/p.png"

    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service.read_profile_image_attachment",
        AsyncMock(return_value=MagicMock(data=b"fake-png")),
    )

    channel = MagicMock()
    channel.permissions_for.return_value = MagicMock(
        view_channel=True,
        send_messages=True,
        embed_links=True,
    )
    channel.send = AsyncMock(return_value=MagicMock(id=9001))
    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service.resolve_hub_category",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.onboarding.service.resolve_hub_channel",
        MagicMock(return_value=channel),
    )
    monkeypatch.setattr(
        "bot.features.channels.resolve.resolve_human_moderator_role",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.core.relay.delivery.build_moderator_join_request_send_kwargs",
        MagicMock(return_value={}),
    )

    service = ServerRequestService(context, bot, view_registry=make_test_view_registry())
    result = await service.submit_request(
        guild,
        requester=requester,
        server_name="Acme Community",
        profile_image=profile_image,
    )

    assert result.success is True
    assert result.server_name == "Acme Community"
    assert result.display_name == "Acme Community"

    stored = await context.store.requests.list_pending()
    assert len(stored) == 1
    assert stored[0].server_name == "Acme Community"
    assert stored[0].display_name == "Acme Community"
