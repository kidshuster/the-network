from __future__ import annotations

from dataclasses import dataclass

import discord

from bot.domain.errors import NetworkValidationError, ProfileValidationError
from bot.services.channel_names import (
    build_client_profile_channel_base,
    build_unique_channel_name,
    slugify_client_name,
)
from bot.services.guild_permissions import (
    build_client_category_overwrites,
    build_client_profile_channel_overwrites,
    create_text_channel_with_overwrites,
    filter_configurable_overwrites,
    prepare_category_create_overwrites,
)
from bot.services.network_provision import (
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
        from bot.services.guild_layout import resolve_human_moderator_role

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

        from bot.services.guild_permissions import build_client_role_name

        role_name = build_unique_role_name(guild, build_client_role_name(server_name))
        client_role = await guild.create_role(
            name=role_name,
            mentionable=False,
            hoist=False,
            reason=f"Client access for {server_name}",
        )

        category_overwrites = prepare_category_create_overwrites(
            bot_member,
            filter_configurable_overwrites(
                bot_member,
                build_client_category_overwrites(
                    guild,
                    bot_member,
                    client_role,
                    access_role,
                    human_moderator_role,
                ),
            ),
        )
        from bot.services.guild_notifications import ensure_guild_only_mention_notifications

        await ensure_guild_only_mention_notifications(
            guild,
            bot_member,
            reason=f"Client provision for {server_name}",
        )
        category = await guild.create_category(
            name=server_name.strip()[:100],
            overwrites=category_overwrites,
            reason=f"Client category for {server_name}",
        )

        profile_overwrites = filter_configurable_overwrites(
            bot_member,
            build_client_profile_channel_overwrites(
                guild,
                bot_member,
                client_role,
                access_role,
                human_moderator_role,
            ),
            for_channel=True,
        )
        profile_channel = await create_text_channel_with_overwrites(
            guild,
            bot_member,
            name=build_unique_channel_name(
                guild,
                build_client_profile_channel_base(server_name),
            ),
            category=category,
            overwrites=profile_overwrites,
            topic=f"Profile and network subscriptions for {server_name}",
            reason=f"Client profile channel for {server_name}",
        )

        return ClientProvisionResult(
            client_role=client_role,
            category=category,
            profile_channel=profile_channel,
        )
