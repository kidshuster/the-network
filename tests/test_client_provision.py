from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles

from bot.clients.provision import (
    ClientProvisionService,
    build_unique_role_name,
)
from bot.domain.errors import NetworkValidationError, ProfileValidationError


def test_build_unique_role_name_suffixes_on_collision() -> None:
    guild = MagicMock(spec=discord.Guild)
    existing = MagicMock(spec=discord.Role)
    existing.name = "Client: Acme"
    guild.roles = [existing]
    assert build_unique_role_name(guild, "Client: Acme") == "Client: Acme-2"


@pytest.mark.asyncio
async def test_provision_client_creates_role_category_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, operator = make_guild_with_roles()

    client_role = MagicMock(spec=discord.Role, id=601, position=1)
    client_role.is_default.return_value = False
    category = MagicMock(spec=discord.CategoryChannel, id=602)
    profile = MagicMock(spec=discord.TextChannel, id=603)

    guild.create_role = AsyncMock(return_value=client_role)
    guild.create_category = AsyncMock(return_value=category)
    guild.roles = [*guild.roles, client_role]

    monkeypatch.setattr(
        "bot.clients.provision.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.clients.provision.resolve_access_role",
        MagicMock(return_value=access),
    )
    monkeypatch.setattr(
        "bot.clients.provision.validate_provision_permissions",
        MagicMock(),
    )
    monkeypatch.setattr(
        "bot.hub.resolve.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.hub.notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )
    from bot.layout.applier import BatchApplyResult, ResourceApplyResult

    batch = BatchApplyResult(
        results=[
            ResourceApplyResult(
                resource_id="client",
                success=True,
                channel=category,
            ),
            ResourceApplyResult(
                resource_id="profile",
                success=True,
                channel=profile,
            ),
        ]
    )
    monkeypatch.setattr(
        "bot.clients.provision.apply_layout",
        AsyncMock(return_value=batch),
    )
    monkeypatch.setattr(
        "bot.clients.provision.build_unique_channel_name",
        MagicMock(return_value="acme-profile"),
    )

    service = ClientProvisionService()
    result = await service.provision_client(
        guild,
        bot,
        server_name="Acme",
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.client_role is client_role
    assert result.category is category
    assert result.profile_channel is profile
    guild.create_role.assert_awaited_once()


@pytest.mark.asyncio
async def test_provision_client_requires_manage_roles() -> None:
    guild, bot, _, _, _ = make_guild_with_roles()
    bot.guild_permissions.manage_roles = False

    service = ClientProvisionService()
    with pytest.raises(ProfileValidationError, match="Manage Roles"):
        await service.provision_client(
            guild,
            bot,
            server_name="Acme",
            access_role_name="The Network",
            operator_role_name="The Network+",
        )


@pytest.mark.asyncio
async def test_provision_client_maps_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, _, _, operator = make_guild_with_roles()
    monkeypatch.setattr(
        "bot.clients.provision.resolve_access_role",
        MagicMock(return_value=MagicMock(spec=discord.Role)),
    )
    monkeypatch.setattr(
        "bot.networks.roles.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.clients.provision.validate_provision_permissions",
        MagicMock(
            side_effect=NetworkValidationError("operator misconfigured"),
        ),
    )

    service = ClientProvisionService()
    with pytest.raises(ProfileValidationError, match="operator misconfigured"):
        await service.provision_client(
            guild,
            bot,
            server_name="Acme",
            access_role_name="The Network",
            operator_role_name="The Network+",
        )
