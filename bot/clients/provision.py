from __future__ import annotations

from dataclasses import dataclass, replace

import discord

from bot.clients.names import (
    build_client_profile_channel_base,
    build_client_role_name,
    build_unique_channel_name,
    slugify_client_name,
)
from bot.domain.errors import NetworkValidationError, ProfileValidationError
from bot.hub.resolve import resolve_human_moderator_role
from bot.layout import ApplyMode, LayoutContext, apply_layout, compile_client
from bot.networks.roles import (
    resolve_access_role,
    resolve_operator_role_by_name,
    validate_provision_permissions,
)


def slugify_server_name(server_name: str) -> str:
    return slugify_client_name(server_name)


def build_unique_role_name(guild: discord.Guild, base_name: str) -> str:
    existing = {role.name.casefold() for role in guild.roles}
    candidate = base_name[:100]
    if candidate.casefold() not in existing:
        return candidate
    for index in range(2, 100):
        suffix = f"-{index}"
        trimmed = base_name[: 100 - len(suffix)] + suffix
        if trimmed.casefold() not in existing:
            return trimmed
    raise ProfileValidationError("Could not allocate a unique client role name.")


@dataclass(frozen=True)
class ClientProvisionResult:
    client_role: discord.Role
    category: discord.CategoryChannel
    profile_channel: discord.TextChannel


class ClientProvisionService:
    async def provision_client(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        server_name: str,
        access_role_name: str,
        operator_role_name: str,
    ) -> ClientProvisionResult:
        if not bot_member.guild_permissions.manage_roles:
            raise ProfileValidationError("Bot needs Manage Roles to create client roles.")
        if not bot_member.guild_permissions.manage_channels:
            raise ProfileValidationError("Bot needs Manage Channels to create client categories.")

        access_role = resolve_access_role(guild, role_name=access_role_name)
        operator_role = resolve_operator_role_by_name(guild, role_name=operator_role_name)
        human_moderator_role = resolve_human_moderator_role(guild)
        try:
            validate_provision_permissions(
                bot_member,
                access_role,
                operator_role=operator_role,
                operator_role_name=operator_role_name,
            )
        except NetworkValidationError as exc:
            raise ProfileValidationError(str(exc)) from exc

        role_name = build_unique_role_name(guild, build_client_role_name(server_name))
        client_role = await guild.create_role(
            name=role_name,
            mentionable=False,
            hoist=False,
            reason=f"Client access for {server_name}",
        )

        slug = slugify_client_name(server_name)
        # Prefer unique profile name via existing helper when collisions exist
        profile_name = build_unique_channel_name(
            guild,
            build_client_profile_channel_base(server_name),
        )
        layout_ctx = LayoutContext(
            guild=guild,
            bot_member=bot_member,
            access_role=access_role,
            moderator_role=human_moderator_role,
            operator_role=operator_role,
            client_role=client_role,
            server_name=server_name.strip()[:100],
            slug=slug,
            reason=f"Client category for {server_name}",
        )
        resources = [
            replace(resource, name=profile_name) if resource.id == "profile" else resource
            for resource in compile_client(layout_ctx, channel_ids={"profile"})
        ]
        batch = await apply_layout(layout_ctx, resources, mode=ApplyMode.ENSURE)
        category = batch.resource("client")
        profile = batch.resource("profile")
        if not isinstance(category, discord.CategoryChannel):
            raise ProfileValidationError("Could not create client category.")
        if not isinstance(profile, discord.TextChannel):
            raise ProfileValidationError("Could not create client profile channel.")

        return ClientProvisionResult(
            client_role=client_role,
            category=category,
            profile_channel=profile,
        )
