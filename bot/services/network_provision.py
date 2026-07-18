from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import discord

from bot.domain.errors import NetworkValidationError
from bot.domain.network import Network
from bot.services.channel_names import build_network_channel_name
from bot.services.discord_errors import DiscordStepError

OverwriteMap = Mapping[
    discord.Role | discord.Member | discord.Object,
    discord.PermissionOverwrite,
]


@dataclass(frozen=True)
class ProvisionedChannels:
    category: discord.CategoryChannel
    profile_forum: discord.ForumChannel


def resolve_access_role(
    guild: discord.Guild,
    *,
    role_name: str,
    explicit_role: discord.Role | None = None,
) -> discord.Role:
    if explicit_role is not None:
        if explicit_role.guild.id != guild.id:
            raise NetworkValidationError("Access role must belong to this guild.")
        return explicit_role

    target = role_name.strip().casefold()
    if not target:
        raise NetworkValidationError("Access role name cannot be empty.")

    for role in guild.roles:
        if role.name.casefold() == target:
            return role

    raise NetworkValidationError(
        f"Could not find access role {role_name!r}. Create the role or pass it explicitly."
    )


def _bot_text_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        manage_channels=True,
        manage_webhooks=True,
        create_public_threads=True,
        send_messages_in_threads=True,
    )


def _bot_forum_overwrite() -> discord.PermissionOverwrite:
    # manage_threads cannot be set in forum creation overwrites (Discord returns 50013).
    # The bot relies on guild-level Manage Threads for moderation after creation.
    return _bot_text_overwrite()


def build_base_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
) -> OverwriteMap:
    return cast(
        OverwriteMap,
        {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            access_role: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
            ),
            bot_member: _bot_text_overwrite(),
        },
    )


def build_feed_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
) -> OverwriteMap:
    overwrites = dict(build_base_overwrites(guild, bot_member, access_role))
    overwrites[access_role] = discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        manage_webhooks=True,
    )
    return cast(OverwriteMap, overwrites)


def build_forum_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
) -> OverwriteMap:
    overwrites = dict(build_base_overwrites(guild, bot_member, access_role))
    overwrites[access_role] = discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        create_public_threads=True,
        send_messages_in_threads=True,
    )
    overwrites[bot_member] = _bot_forum_overwrite()
    return cast(OverwriteMap, overwrites)


def category_name_for(display_name: str) -> str:
    cleaned = display_name.strip() or "Network"
    return f"{cleaned} Feed"[:100]


def validate_provision_permissions(
    bot_member: discord.Member,
    access_role: discord.Role,
) -> None:
    """Ensure the bot can create private categories/channels with role overwrites."""
    perms = bot_member.guild_permissions
    issues: list[str] = []

    if not perms.manage_channels:
        issues.append("**Manage Channels** — required to create categories and channels.")
    if not perms.manage_roles:
        issues.append(
            "**Manage Roles** — required to set private channel permission overwrites. "
            "Manage Channels alone is not enough."
        )
    if not perms.manage_webhooks:
        issues.append("**Manage Webhooks** — required for partner feed channels.")

    if bot_member.top_role.position <= access_role.position:
        bot_label = bot_member.display_name
        if bot_member.top_role.id == access_role.id:
            issues.append(
                f"The bot ({bot_label}) is assigned the role **{access_role.name}**, "
                "and that same role is also used as the network access role. "
                "Discord will not let a role configure channel permissions for itself.\n"
                "Create a separate role for the bot, place it **above** "
                f"**{access_role.name}** in Server Settings → Roles, assign it to "
                f"**{bot_label}**, and give it Manage Channels + Manage Roles."
            )
        else:
            issues.append(
                f"The bot ({bot_label}) needs a role placed **above** "
                f"**{access_role.name}** in Server Settings → Roles. "
                f"Its highest role right now is **{bot_member.top_role.name}**."
            )

    if issues:
        raise NetworkValidationError(
            "Bot cannot provision network infrastructure yet:\n"
            + "\n".join(f"• {item}" for item in issues)
            + "\n\nGive the bot a dedicated role above "
            f"**{access_role.name}** with Manage Channels and Manage Roles."
        )


class NetworkProvisionService:
    async def provision(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        key: str,
        display_name: str,
        output_channel: discord.abc.GuildChannel,
        access_role: discord.Role,
    ) -> ProvisionedChannels:
        if output_channel.guild.id != guild.id:
            raise NetworkValidationError("Output channel must belong to this guild.")
        if getattr(output_channel, "type", None) is not discord.ChannelType.news:
            raise NetworkValidationError(
                f"#{getattr(output_channel, 'name', output_channel.id)} must be an "
                "announcement channel."
            )

        validate_provision_permissions(bot_member, access_role)

        category_overwrites = build_base_overwrites(guild, bot_member, access_role)
        category = await self._run_step(
            "create feed category",
            guild.create_category(
                name=category_name_for(display_name),
                overwrites=category_overwrites,
                reason=f"Provision network {key}",
            ),
        )

        profile_forum = await self._run_step(
            "create #profiles forum",
            guild.create_forum(
                name=build_network_channel_name(guild, key, "profiles"),
                category=category,
                overwrites=build_forum_overwrites(guild, bot_member, access_role),
                reason=f"Profile forum for network {key}",
            ),
        )

        return ProvisionedChannels(
            category=category,
            profile_forum=profile_forum,
        )

    async def _run_step(self, step: str, coro: Any) -> Any:
        try:
            return await coro
        except discord.HTTPException as exc:
            raise DiscordStepError(step, exc) from exc


async def create_guide_thread(
    forum: discord.ForumChannel,
    *,
    network: Network,
) -> discord.Thread:
    embed = discord.Embed(
        title=f"{network.display_name} profiles",
        description=(
            "This forum holds **server profiles** for this network.\n\n"
            "Use `/server create` with:\n"
            f"• **key:** `{network.key}`\n"
            "• **server name**, **profile image**, and **display name**\n\n"
            "Each server gets its own feed channel for Channel Follow."
        ),
        colour=discord.Colour.blurple(),
    )
    embed.add_field(
        name="Output announcements",
        value=f"<#{network.output_channel_id}>",
        inline=False,
    )
    try:
        thread_with_message = await forum.create_thread(
            name="How to add server profiles",
            embed=embed,
            content="\u200b",
        )
    except discord.HTTPException as exc:
        raise DiscordStepError("create profile forum guide thread", exc) from exc
    return thread_with_message.thread
