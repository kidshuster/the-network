from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles

from bot.domain.errors import NetworkValidationError, ProfileValidationError
from bot.services.client_provision import (
    ClientProvisionService,
    build_unique_role_name,
)


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
        "bot.services.client_provision.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.services.client_provision.resolve_access_role",
        MagicMock(return_value=access),
    )
    monkeypatch.setattr(
        "bot.services.client_provision.validate_provision_permissions",
        MagicMock(),
    )
    monkeypatch.setattr(
        "bot.services.guild_layout.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.services.client_provision.create_text_channel_with_overwrites",
        AsyncMock(return_value=profile),
    )
    monkeypatch.setattr(
        "bot.services.client_provision.build_unique_channel_name",
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
    guild.create_category.assert_awaited_once()


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
        "bot.services.client_provision.resolve_access_role",
        MagicMock(return_value=MagicMock(spec=discord.Role)),
    )
    monkeypatch.setattr(
        "bot.services.network_provision.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.services.client_provision.validate_provision_permissions",
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
