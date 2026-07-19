from __future__ import annotations

import logging
from dataclasses import dataclass, field

import discord

from bot.domain.errors import NetworkValidationError
from bot.services.guild_layout import (
    CATEGORY_MODERATION,
    CATEGORY_NETWORK,
    CATEGORY_SUBSCRIBE,
    CHANNEL_COMMANDS,
    CHANNEL_JOIN_REQUESTS,
    CHANNEL_MODERATOR_ONLY,
    CHANNEL_RULES,
    CHANNEL_WELCOME_SINK,
    iter_subscribe_announcement_channels,
    resolve_category,
    resolve_human_moderator_role,
    resolve_moderator_role,
    resolve_welcome_sink_channel,
)
from bot.services.guild_permissions import (
    build_commands_channel_overwrites,
    build_hub_public_category_overwrites,
    build_moderation_staff_overwrites,
    build_subscribe_announcement_channel_overwrites,
    build_subscribe_category_overwrites,
    build_welcome_sink_overwrites,
)
from bot.services.network_provision import resolve_access_role, validate_hub_permissions

logger = logging.getLogger(__name__)

_MODERATOR_GUILD_PERMISSIONS = discord.Permissions(
    view_channel=True,
    send_messages=True,
    embed_links=True,
    attach_files=True,
    read_message_history=True,
    manage_messages=True,
    manage_channels=True,
    manage_roles=True,
    manage_webhooks=True,
    mention_everyone=False,
)


@dataclass
class GuildInitResult:
    success: bool
    created_categories: list[str] = field(default_factory=list)
    created_channels: list[str] = field(default_factory=list)
    moved_channels: list[str] = field(default_factory=list)
    updated_roles: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reason: str | None = None


async def _ensure_category(
    guild: discord.Guild,
    bot_member: discord.Member,
    display_name: str,
    overwrites: dict,
    *,
    result: GuildInitResult,
) -> discord.CategoryChannel:
    existing = resolve_category(guild, display_name)
    if existing is not None:
        await existing.edit(overwrites=overwrites, reason="The Network guild init")
        return existing
    created = await guild.create_category(
        name=display_name,
        overwrites=overwrites,
        reason="The Network guild init",
    )
    result.created_categories.append(display_name)
    return created


async def _ensure_text_channel(
    guild: discord.Guild,
    *,
    name: str,
    category: discord.CategoryChannel,
    overwrites: dict,
    topic: str | None,
    result: GuildInitResult,
) -> discord.TextChannel:
    for channel in guild.text_channels:
        if channel.name.casefold() == name.casefold() and channel.category_id == category.id:
            await channel.edit(
                overwrites=overwrites,
                name=name,
                topic=topic,
                reason="The Network guild init",
            )
            return channel

    for channel in guild.text_channels:
        if channel.name.casefold() == name.casefold():
            await channel.edit(
                category=category,
                overwrites=overwrites,
                name=name,
                topic=topic,
                reason="The Network guild init",
            )
            result.moved_channels.append(f"#{name} → {category.name}")
            return channel

    created = await guild.create_text_channel(
        name=name,
        category=category,
        overwrites=overwrites,
        topic=topic,
        reason="The Network guild init",
    )
    result.created_channels.append(f"#{name}")
    return created


async def _ensure_moderator_role(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    role_name: str,
    result: GuildInitResult,
) -> discord.Role:
    role = resolve_moderator_role(guild, role_name=role_name)
    if role is None:
        role = await guild.create_role(
            name=role_name,
            permissions=_MODERATOR_GUILD_PERMISSIONS,
            mentionable=False,
            hoist=True,
            reason="The Network guild init",
        )
        result.updated_roles.append(f"Created {role_name}")
        return role

    if bot_member.top_role.id == role.id:
        result.notes.append(
            f"The bot is assigned **{role.name}** — skipped editing that role's "
            "guild permissions. Ensure that role has the staff permissions you want."
        )
        return role

    if bot_member.top_role.position <= role.position:
        result.notes.append(
            f"Skipped updating **{role.name}** — the bot's role "
            f"(**{bot_member.top_role.name}**) must be above **{role.name}** "
            "in the role list."
        )
        return role

    await role.edit(permissions=_MODERATOR_GUILD_PERMISSIONS, reason="The Network guild init")
    result.updated_roles.append(f"Updated {role.name}")
    return role


async def _ensure_access_role(
    guild: discord.Guild,
    role_name: str,
    *,
    result: GuildInitResult,
) -> discord.Role:
    role = resolve_access_role(guild, role_name=role_name)
    result.updated_roles.append(f"Using access role {role.name}")
    return role


async def _move_rules_channel(
    guild: discord.Guild,
    network_category: discord.CategoryChannel,
    overwrites: dict,
    *,
    result: GuildInitResult,
) -> None:
    rules = guild.rules_channel
    if isinstance(rules, discord.TextChannel):
        if rules.category_id != network_category.id or rules.name != CHANNEL_RULES:
            await rules.edit(
                category=network_category,
                name=CHANNEL_RULES,
                overwrites=overwrites,
                reason="The Network guild init",
            )
            result.moved_channels.append(f"{rules.mention} → {CATEGORY_NETWORK}/{CHANNEL_RULES}")
        return

    await _ensure_text_channel(
        guild,
        name=CHANNEL_RULES,
        category=network_category,
        overwrites=overwrites,
        topic="Hub relay rules for The Network",
        result=result,
    )
    result.notes.append(
        "Set this channel as the Community rules channel under Server Settings if needed."
    )


async def _find_moderator_only_channel(guild: discord.Guild) -> discord.TextChannel | None:
    for channel in guild.text_channels:
        lowered = channel.name.casefold()
        if lowered in {"moderator-only", "mod-only", "staff-only"}:
            return channel
    return None


async def _ensure_welcome_sink_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    result: GuildInitResult,
) -> discord.TextChannel:
    overwrites = dict(build_welcome_sink_overwrites(guild, bot_member))
    sink = resolve_welcome_sink_channel(guild)
    if sink is None:
        sink = await guild.create_text_channel(
            name=CHANNEL_WELCOME_SINK,
            overwrites=overwrites,
            reason="The Network guild init",
        )
        result.created_channels.append(f"#{CHANNEL_WELCOME_SINK} (hidden)")
    else:
        await sink.edit(overwrites=overwrites, reason="The Network guild init")

    if sink.position != 0:
        await sink.edit(position=0, reason="The Network guild init")
        result.notes.append(
            f"Moved #{CHANNEL_WELCOME_SINK} to the top to absorb Discord's welcome message."
        )
    return sink


async def _sync_subscribe_announcement_channels(
    guild: discord.Guild,
    bot_member: discord.Member,
    subscribe_category: discord.CategoryChannel,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    *,
    result: GuildInitResult,
) -> None:
    overwrites = dict(
        build_subscribe_announcement_channel_overwrites(
            guild, bot_member, access_role, human_moderator_role
        )
    )
    for channel in iter_subscribe_announcement_channels(guild, subscribe_category):
        await channel.edit(overwrites=overwrites, reason="The Network guild init")
        label = f"#{channel.name}" if hasattr(channel, "name") else str(channel.id)
        result.notes.append(f"Synced public subscribe permissions on {label}")


async def initialize_guild(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    access_role_name: str,
    moderator_role_name: str,
) -> GuildInitResult:
    result = GuildInitResult(success=True)
    perms = bot_member.guild_permissions
    if not perms.manage_channels or not perms.manage_roles:
        return GuildInitResult(
            success=False,
            reason=(
                "The bot needs **Manage Channels** and **Manage Roles** "
                "to initialize the guild."
            ),
        )

    try:
        access_role = await _ensure_access_role(guild, access_role_name, result=result)
        if access_role in bot_member.roles:
            result.notes.append(
                f"The bot is assigned **{access_role.name}**, which is also the network "
                "access role. Remove that role from the bot and keep it for staff/partners only."
            )
        moderator_role = resolve_moderator_role(guild, role_name=moderator_role_name)
        validate_hub_permissions(
            bot_member,
            access_role,
            moderator_role=moderator_role,
        )
        moderator_role = await _ensure_moderator_role(
            guild,
            bot_member,
            role_name=moderator_role_name,
            result=result,
        )
        human_moderator_role = resolve_human_moderator_role(guild)
        if human_moderator_role is None:
            result.notes.append(
                "Could not find a human **Moderator** role — moderation channels are "
                "bot-only until you create that role and run `/network init` again."
            )

        await _ensure_welcome_sink_channel(guild, bot_member, result=result)

        subscribe = await _ensure_category(
            guild,
            bot_member,
            CATEGORY_SUBSCRIBE,
            dict(build_subscribe_category_overwrites(
                guild, bot_member, access_role, human_moderator_role
            )),
            result=result,
        )
        network_cat = await _ensure_category(
            guild,
            bot_member,
            CATEGORY_NETWORK,
            dict(build_hub_public_category_overwrites(
                guild, bot_member, access_role, human_moderator_role
            )),
            result=result,
        )
        moderation = await _ensure_category(
            guild,
            bot_member,
            CATEGORY_MODERATION,
            dict(build_moderation_staff_overwrites(guild, bot_member, human_moderator_role)),
            result=result,
        )

        rules_overwrites = dict(
            build_hub_public_category_overwrites(
                guild, bot_member, access_role, human_moderator_role
            )
        )
        await _move_rules_channel(guild, network_cat, rules_overwrites, result=result)

        mod_only_source = await _find_moderator_only_channel(guild)
        mod_only_overwrites = dict(
            build_moderation_staff_overwrites(guild, bot_member, human_moderator_role)
        )
        if mod_only_source is not None and mod_only_source.category_id != moderation.id:
            await mod_only_source.edit(
                category=moderation,
                name=CHANNEL_MODERATOR_ONLY,
                overwrites=mod_only_overwrites,
                reason="The Network guild init",
            )
            result.moved_channels.append(
                f"{mod_only_source.mention} → {CATEGORY_MODERATION}/{CHANNEL_MODERATOR_ONLY}"
            )
        else:
            await _ensure_text_channel(
                guild,
                name=CHANNEL_MODERATOR_ONLY,
                category=moderation,
                overwrites=mod_only_overwrites,
                topic="Moderator discussion",
                result=result,
            )

        await _ensure_text_channel(
            guild,
            name=CHANNEL_JOIN_REQUESTS,
            category=moderation,
            overwrites=mod_only_overwrites,
            topic="Pending partner join requests",
            result=result,
        )
        await _ensure_text_channel(
            guild,
            name=CHANNEL_COMMANDS,
            category=moderation,
            overwrites=dict(
                build_commands_channel_overwrites(guild, bot_member, human_moderator_role)
            ),
            topic="Run The Network bot commands here",
            result=result,
        )

        for category in guild.categories:
            if category.id in {subscribe.id, network_cat.id, moderation.id}:
                continue
            if category.name.casefold().endswith(" feed"):
                await category.edit(
                    overwrites=dict(
                        build_subscribe_category_overwrites(
                            guild, bot_member, access_role, human_moderator_role
                        )
                    ),
                    reason="The Network guild init",
                )
                result.notes.append(f"Synced permissions on feed category {category.name}")

        await _ensure_welcome_sink_channel(guild, bot_member, result=result)

        await _sync_subscribe_announcement_channels(
            guild,
            bot_member,
            subscribe,
            access_role,
            human_moderator_role,
            result=result,
        )

        result.notes.append(
            f"Place network announcement outputs in **{CATEGORY_SUBSCRIBE}**. "
            f"Partner feeds are created under each network's feed category."
        )
    except discord.HTTPException as exc:
        logger.warning("Guild init failed", extra={"error": str(exc)})
        return GuildInitResult(success=False, reason=f"Discord API error during init: {exc}")
    except NetworkValidationError as exc:
        return GuildInitResult(success=False, reason=str(exc))

    return result
