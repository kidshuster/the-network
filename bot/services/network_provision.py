from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import discord

from bot.domain.errors import NetworkValidationError
from bot.services.channel_names import build_network_channel_name, build_unique_channel_name
from bot.services.discord_errors import DiscordStepError
from bot.services.guild_channels import join_channel_name, resolve_network_hub_category
from bot.services.guild_layout import (
    CATEGORY_SUBSCRIBE,
    resolve_human_moderator_role,
    resolve_moderator_role,
    resolve_network_announcement_channel,
    resolve_subscribe_category,
)
from bot.services.guild_permissions import (
    build_feed_category_overwrites,
    build_join_channel_overwrites,
    build_subscribe_announcement_channel_overwrites,
    filter_configurable_overwrites,
)

OverwriteMap = Mapping[
    discord.Role | discord.Member | discord.Object,
    discord.PermissionOverwrite,
]


@dataclass(frozen=True)
class ProvisionedChannels:
    feed_category: discord.CategoryChannel
    join_channel: discord.TextChannel
    output_channel: discord.abc.GuildChannel
    created_output_channel: bool = False


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
    )


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


def category_name_for(display_name: str) -> str:
    cleaned = display_name.strip() or "Network"
    return f"{cleaned} Feed"[:100]


async def create_announcement_channel(
    guild: discord.Guild,
    *,
    name: str,
    category: discord.CategoryChannel,
    overwrites: OverwriteMap,
    reason: str,
) -> discord.abc.GuildChannel:
    """Create an announcement channel (discord.py uses create_text_channel(news=True))."""
    return await guild.create_text_channel(
        name=name,
        category=category,
        overwrites=overwrites,
        news=True,
        reason=reason,
    )


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

    top = bot_member.top_role
    if top.id == access_role.id:
        issues.append(
            f"The bot is assigned **{access_role.name}**, which is also the configured "
            "network **access role**. Discord will not let a role configure channel "
            "permissions for itself.\n"
            "Use two roles:\n"
            f"• A **bot-only role** at the **top** of the role list (Manage Channels + "
            "Manage Roles + Manage Webhooks)\n"
            f"• **{access_role.name}** below it for staff/partners (not assigned to the bot)"
        )
    elif top.position <= access_role.position:
        issues.append(
            f"The bot's highest role (**{top.name}**, position {top.position}) must be "
            f"**above** **{access_role.name}** (position {access_role.position}) in "
            "Server Settings → Roles. Drag the bot's role toward the top of the list."
        )

    if issues:
        raise NetworkValidationError(
            "Bot cannot provision network infrastructure yet:\n"
            + "\n".join(f"• {item}" for item in issues)
            + "\n\nGive the bot a dedicated role above "
            f"**{access_role.name}** with Manage Channels and Manage Roles."
        )


def validate_hub_permissions(
    bot_member: discord.Member,
    access_role: discord.Role,
    *,
    moderator_role: discord.Role | None,
) -> None:
    """Ensure the bot can run `/network init` and configure hub channel overwrites."""
    validate_provision_permissions(bot_member, access_role)

    if moderator_role is None:
        return

    top = bot_member.top_role
    if top.id == moderator_role.id:
        return

    if top.position <= moderator_role.position:
        raise NetworkValidationError(
            "Bot cannot initialize the hub yet:\n"
            f"• The bot's highest role (**{top.name}**, position {top.position}) must be "
            f"**above** **{moderator_role.name}** (position {moderator_role.position}) "
            "in Server Settings → Roles.\n\n"
            "Drag the bot's dedicated role to the **top** of the role list (below only "
            "owner/admin roles), then run `/network init` again."
        )


class NetworkProvisionService:
    async def ensure_announcement_output_channel(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        key: str,
        access_role: discord.Role,
        human_moderator_role: discord.Role | None,
    ) -> tuple[discord.abc.GuildChannel, bool]:
        subscribe_category = resolve_subscribe_category(guild)
        if subscribe_category is None:
            raise NetworkValidationError(
                f'Could not find **{CATEGORY_SUBSCRIBE}**. Run `/network init` first.'
            )

        existing = resolve_network_announcement_channel(
            guild,
            key,
            category=subscribe_category,
        )
        announcement_overwrites = filter_configurable_overwrites(
            bot_member,
            dict(
                build_subscribe_announcement_channel_overwrites(
                    guild,
                    bot_member,
                    access_role,
                    human_moderator_role,
                )
            ),
        )
        if existing is not None:
            await self._run_step(
                "sync announcement output channel permissions",
                existing.edit(
                    overwrites=announcement_overwrites,
                    reason=f"Sync announcement output for network {key}",
                ),
            )
            return existing, False

        channel_name = build_network_channel_name(guild, key, "announcements")
        created = await self._run_step(
            "create announcement output channel",
            create_announcement_channel(
                guild,
                name=channel_name,
                category=subscribe_category,
                overwrites=announcement_overwrites,
                reason=f"Announcement output for network {key}",
            ),
        )
        return created, True

    async def provision(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        *,
        key: str,
        display_name: str,
        output_channel: discord.abc.GuildChannel | None,
        access_role: discord.Role,
    ) -> ProvisionedChannels:
        validate_provision_permissions(bot_member, access_role)
        bot_staff_role = resolve_moderator_role(guild)
        if bot_staff_role is None:
            raise NetworkValidationError(
                "Could not find the bot staff role. Run `/network init` first."
            )
        human_moderator_role = resolve_human_moderator_role(guild)

        created_output = False
        if output_channel is None:
            output_channel, created_output = await self.ensure_announcement_output_channel(
                guild,
                bot_member,
                key=key,
                access_role=access_role,
                human_moderator_role=human_moderator_role,
            )
        elif output_channel.guild.id != guild.id:
            raise NetworkValidationError("Output channel must belong to this guild.")
        elif getattr(output_channel, "type", None) is not discord.ChannelType.news:
            raise NetworkValidationError(
                f"#{getattr(output_channel, 'name', output_channel.id)} must be an "
                "announcement channel."
            )
        else:
            subscribe_category = resolve_subscribe_category(guild)
            if (
                subscribe_category is not None
                and output_channel.category_id == subscribe_category.id
            ):
                announcement_overwrites = filter_configurable_overwrites(
                    bot_member,
                    dict(
                        build_subscribe_announcement_channel_overwrites(
                            guild,
                            bot_member,
                            access_role,
                            human_moderator_role,
                        )
                    ),
                )
                await self._run_step(
                    "sync announcement output channel permissions",
                    output_channel.edit(
                        overwrites=announcement_overwrites,
                        reason=f"Sync announcement output for network {key}",
                    ),
                )

        category_overwrites = build_feed_category_overwrites(
            guild, bot_member, access_role, human_moderator_role
        )
        feed_category = await self._run_step(
            "create feed category",
            guild.create_category(
                name=category_name_for(display_name),
                overwrites=category_overwrites,
                reason=f"Provision network {key} feeds",
            ),
        )

        join_channel = await self._create_join_channel(
            guild,
            key=key,
            access_role=access_role,
            bot_member=bot_member,
        )

        return ProvisionedChannels(
            feed_category=feed_category,
            join_channel=join_channel,
            output_channel=output_channel,
            created_output_channel=created_output,
        )

    async def _create_join_channel(
        self,
        guild: discord.Guild,
        *,
        key: str,
        access_role: discord.Role,
        bot_member: discord.Member,
    ) -> discord.TextChannel:
        hub_category = resolve_network_hub_category(guild)
        if hub_category is None:
            raise NetworkValidationError(
                'Could not find a **The Network** category. Run `/network init` first.'
            )

        human_moderator_role = resolve_human_moderator_role(guild)

        overwrites = build_join_channel_overwrites(
            guild, bot_member, access_role, human_moderator_role
        )
        channel_name = build_unique_channel_name(guild, join_channel_name(key))
        return await self._run_step(
            "create join channel",
            guild.create_text_channel(
                name=channel_name,
                category=hub_category,
                overwrites=overwrites,
                reason=f"Join guide channel for network {key}",
            ),
        )

    async def _run_step(self, step: str, coro: Any) -> Any:
        try:
            return await coro
        except discord.HTTPException as exc:
            raise DiscordStepError(step, exc) from exc
