from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

import discord

from bot.domain.errors import NetworkValidationError, ProfileValidationError
from bot.services.channel_names import build_network_channel_name
from bot.services.network_provision import (
    OverwriteMap,
    resolve_access_role,
    validate_provision_permissions,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_server_name(server_name: str) -> str:
    slug = _SLUG_RE.sub("-", server_name.strip().lower()).strip("-")
    return slug[:32] if slug else "partner"


def build_partner_role_name(server_name: str) -> str:
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
    raise ProfileValidationError("Could not allocate a unique partner role name.")


def build_partner_feed_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    partner_role: discord.Role,
    admin_role: discord.Role,
) -> OverwriteMap:
    return cast(
        OverwriteMap,
        {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            partner_role: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                manage_webhooks=True,
            ),
            admin_role: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                manage_webhooks=True,
                manage_channels=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                manage_webhooks=True,
                manage_channels=True,
            ),
        },
    )


def build_partner_forum_member_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        create_public_threads=True,
        send_messages_in_threads=True,
    )


@dataclass(frozen=True)
class PartnerProvisionResult:
    partner_role: discord.Role
    feed_channel: discord.TextChannel
    profile_forum: discord.ForumChannel


class ProfileProvisionService:
    async def provision_partner(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        network_key: str,
        server_name: str,
        feed_category_id: int,
        profile_forum_channel_id: int,
        admin_role_name: str,
    ) -> PartnerProvisionResult:
        if not bot_member.guild_permissions.manage_roles:
            raise ProfileValidationError("Bot needs Manage Roles to create partner access roles.")
        if not bot_member.guild_permissions.manage_channels:
            raise ProfileValidationError(
                "Bot needs Manage Channels to create partner feed and profile channels."
            )

        admin_role = resolve_access_role(guild, role_name=admin_role_name)
        try:
            validate_provision_permissions(bot_member, admin_role)
        except NetworkValidationError as exc:
            raise ProfileValidationError(str(exc)) from exc

        category = guild.get_channel(feed_category_id)
        if not isinstance(category, discord.CategoryChannel):
            fetched = await guild.fetch_channel(feed_category_id)
            if not isinstance(fetched, discord.CategoryChannel):
                raise ProfileValidationError("Network feed category could not be loaded.")
            category = fetched

        profile_forum = guild.get_channel(profile_forum_channel_id)
        if not isinstance(profile_forum, discord.ForumChannel):
            fetched_forum = await guild.fetch_channel(profile_forum_channel_id)
            if not isinstance(fetched_forum, discord.ForumChannel):
                raise ProfileValidationError(
                    "Network profiles forum could not be loaded. "
                    "Re-run `/network create` or register a valid profiles forum."
                )
            profile_forum = fetched_forum

        slug = slugify_server_name(server_name)
        role_name = build_unique_role_name(guild, build_partner_role_name(server_name))
        partner_role = await guild.create_role(
            name=role_name,
            mentionable=False,
            hoist=False,
            reason=f"Partner access for {server_name} on network {network_key}",
        )

        feed_name = build_network_channel_name(guild, network_key, f"{slug}-feed")
        overwrites_feed = build_partner_feed_overwrites(
            guild,
            bot_member,
            partner_role,
            admin_role,
        )

        feed_channel: discord.TextChannel | None = None
        try:
            feed_channel = await guild.create_text_channel(
                name=feed_name,
                category=category,
                overwrites=overwrites_feed,
                reason=f"Partner feed for {server_name} ({network_key})",
            )
            await profile_forum.set_permissions(
                partner_role,
                overwrite=build_partner_forum_member_overwrite(),
                reason=f"Partner access to network profiles forum ({server_name})",
            )
        except discord.HTTPException:
            try:
                await partner_role.delete(reason="Partner provisioning failed")
            except discord.HTTPException:
                pass
            if feed_channel is not None:
                try:
                    await feed_channel.delete(reason="Partner provisioning failed")
                except discord.HTTPException:
                    pass
            raise

        return PartnerProvisionResult(
            partner_role=partner_role,
            feed_channel=feed_channel,
            profile_forum=profile_forum,
        )
