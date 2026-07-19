from __future__ import annotations

import re
from dataclasses import dataclass

import discord

from bot.domain.errors import NetworkValidationError, ProfileValidationError
from bot.services.channel_names import build_network_channel_name
from bot.services.guild_layout import resolve_human_moderator_role
from bot.services.guild_permissions import (
    build_server_feed_channel_overwrites,
)
from bot.services.network_provision import (
    resolve_access_role,
    validate_provision_permissions,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_server_name(server_name: str) -> str:
    slug = _SLUG_RE.sub("-", server_name.strip().lower()).strip("-")
    return slug[:32] if slug else "server"


def build_server_role_name(server_name: str) -> str:
    return f"Partner: {server_name.strip()}"[:100]


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
    raise ProfileValidationError("Could not allocate a unique server access role name.")


@dataclass(frozen=True)
class ServerProvisionResult:
    server_role: discord.Role
    feed_channel: discord.TextChannel


class ProfileProvisionService:
    async def provision_server(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        network_key: str,
        server_name: str,
        feed_category_id: int,
        admin_role_name: str,
    ) -> ServerProvisionResult:
        if not bot_member.guild_permissions.manage_roles:
            raise ProfileValidationError("Bot needs Manage Roles to create server access roles.")
        if not bot_member.guild_permissions.manage_channels:
            raise ProfileValidationError(
                "Bot needs Manage Channels to create server feed channels."
            )

        admin_role = resolve_access_role(guild, role_name=admin_role_name)
        human_moderator_role = resolve_human_moderator_role(guild)
        try:
            validate_provision_permissions(bot_member, admin_role)
        except NetworkValidationError as exc:
            raise ProfileValidationError(str(exc)) from exc

        feed_category = await self._fetch_category(guild, feed_category_id, "feed")

        slug = slugify_server_name(server_name)
        role_name = build_unique_role_name(guild, build_server_role_name(server_name))
        server_role = await guild.create_role(
            name=role_name,
            mentionable=False,
            hoist=False,
            reason=f"Server access for {server_name} on network {network_key}",
        )

        feed_name = build_network_channel_name(guild, network_key, slug)

        feed_channel: discord.TextChannel | None = None
        try:
            feed_channel = await guild.create_text_channel(
                name=feed_name,
                category=feed_category,
                overwrites=build_server_feed_channel_overwrites(
                    guild,
                    bot_member,
                    server_role,
                    admin_role,
                    human_moderator_role,
                ),
                reason=f"Server feed for {server_name} ({network_key})",
            )
        except discord.HTTPException:
            if feed_channel is not None:
                try:
                    await feed_channel.delete(reason="Server provisioning failed")
                except discord.HTTPException:
                    pass
            try:
                await server_role.delete(reason="Server provisioning failed")
            except discord.HTTPException:
                pass
            raise

        return ServerProvisionResult(
            server_role=server_role,
            feed_channel=feed_channel,
        )

    async def _fetch_category(
        self,
        guild: discord.Guild,
        category_id: int,
        label: str,
    ) -> discord.CategoryChannel:
        channel = guild.get_channel(category_id)
        if channel is None:
            fetched = await guild.fetch_channel(category_id)
            channel = fetched

        if isinstance(channel, discord.ForumChannel):
            raise ProfileValidationError(
                f"Network {label} is configured as a forum (<#{channel.id}>). "
                "Re-run `/network create` so the network uses a feed category."
            )
        if not isinstance(channel, discord.CategoryChannel):
            raise ProfileValidationError(
                f"Network {label} category could not be loaded (expected a category, "
                f"got {type(channel).__name__}). Re-run `/network create`."
            )
        return channel
