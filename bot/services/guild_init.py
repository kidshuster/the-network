from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord

from bot.domain.errors import NetworkValidationError
from bot.domain.profile import ServerProfile
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
    build_server_feed_channel_overwrites,
    build_subscribe_announcement_channel_overwrites,
    build_subscribe_category_overwrites,
    build_welcome_sink_overwrites,
    filter_configurable_overwrites,
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
    failed_steps: list[str] = field(default_factory=list)
    reason: str | None = None


async def _run_init_step[T](
    result: GuildInitResult,
    step: str,
    action: Callable[[], Awaitable[T]],
    *,
    fallback: T | None = None,
) -> T | None:
    try:
        return await action()
    except discord.HTTPException as exc:
        message = f"{step}: {exc}"
        result.failed_steps.append(message)
        result.notes.append(f"Could not {step}: {exc}")
        logger.warning("Guild init step failed", extra={"step": step, "error": str(exc)})
        return fallback


async def _edit_overwrites(
    bot_member: discord.Member,
    target: discord.abc.GuildChannel,
    overwrites: dict,
    *,
    result: GuildInitResult,
    step: str,
    **edit_kwargs: object,
) -> bool:
    safe_overwrites = filter_configurable_overwrites(bot_member, overwrites)

    async def _edit() -> None:
        await target.edit(
            overwrites=safe_overwrites,
            reason="The Network guild init",
            **edit_kwargs,  # type: ignore[arg-type]
        )

    edited = await _run_init_step(result, step, _edit)
    return edited is not None


async def _ensure_category(
    guild: discord.Guild,
    bot_member: discord.Member,
    display_name: str,
    overwrites: dict,
    *,
    result: GuildInitResult,
) -> discord.CategoryChannel | None:
    existing = resolve_category(guild, display_name)
    if existing is not None:
        await _edit_overwrites(
            bot_member,
            existing,
            overwrites,
            result=result,
            step=f"sync {display_name} category permissions",
        )
        return existing

    safe_overwrites = filter_configurable_overwrites(bot_member, overwrites)

    async def _create() -> discord.CategoryChannel:
        return await guild.create_category(
            name=display_name,
            overwrites=safe_overwrites,
            reason="The Network guild init",
        )

    created = await _run_init_step(result, f"create {display_name} category", _create)
    if created is not None:
        result.created_categories.append(display_name)
    return created


async def _ensure_text_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    name: str,
    category: discord.CategoryChannel,
    overwrites: dict,
    topic: str | None,
    result: GuildInitResult,
) -> discord.TextChannel | None:
    safe_overwrites = filter_configurable_overwrites(bot_member, overwrites)

    for channel in guild.text_channels:
        if channel.name.casefold() == name.casefold() and channel.category_id == category.id:
            await _edit_overwrites(
                bot_member,
                channel,
                overwrites,
                result=result,
                step=f"sync #{name} permissions",
                name=name,
                topic=topic,
            )
            return channel

    for channel in guild.text_channels:
        if channel.name.casefold() == name.casefold():
            moved = await _edit_overwrites(
                bot_member,
                channel,
                overwrites,
                result=result,
                step=f"move #{name} into {category.name}",
                category=category,
                name=name,
                topic=topic,
            )
            if moved:
                result.moved_channels.append(f"#{name} → {category.name}")
            return channel

    async def _create() -> discord.TextChannel:
        return await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=safe_overwrites,
            topic=topic,
            reason="The Network guild init",
        )

    created = await _run_init_step(result, f"create #{name}", _create)
    if created is not None:
        result.created_channels.append(f"#{name}")
    return created


async def _ensure_moderator_role(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    role_name: str,
    result: GuildInitResult,
) -> discord.Role | None:
    role = resolve_moderator_role(guild, role_name=role_name)
    if role is None:

        async def _create() -> discord.Role:
            return await guild.create_role(
                name=role_name,
                permissions=_MODERATOR_GUILD_PERMISSIONS,
                mentionable=False,
                hoist=True,
                reason="The Network guild init",
            )

        created = await _run_init_step(result, f"create {role_name} role", _create)
        if created is not None:
            result.updated_roles.append(f"Created {role_name}")
        return created

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

    async def _update() -> discord.Role:
        await role.edit(permissions=_MODERATOR_GUILD_PERMISSIONS, reason="The Network guild init")
        return role

    updated = await _run_init_step(result, f"update {role.name} role permissions", _update)
    if updated is not None:
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
    bot_member: discord.Member,
    network_category: discord.CategoryChannel,
    overwrites: dict,
    *,
    result: GuildInitResult,
) -> None:
    rules = guild.rules_channel
    if isinstance(rules, discord.TextChannel):
        edit_kwargs: dict[str, object] = {}
        if rules.category_id != network_category.id or rules.name != CHANNEL_RULES:
            edit_kwargs["category"] = network_category
            edit_kwargs["name"] = CHANNEL_RULES
        synced = await _edit_overwrites(
            bot_member,
            rules,
            overwrites,
            result=result,
            step=f"sync rules channel {rules.mention}",
            **edit_kwargs,
        )
        if synced and edit_kwargs:
            result.moved_channels.append(f"{rules.mention} → {CATEGORY_NETWORK}/{CHANNEL_RULES}")
        return

    await _ensure_text_channel(
        guild,
        bot_member,
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
) -> discord.TextChannel | None:
    overwrites = dict(build_welcome_sink_overwrites(guild, bot_member))
    sink = resolve_welcome_sink_channel(guild)
    if sink is None:

        async def _create() -> discord.TextChannel:
            safe = filter_configurable_overwrites(bot_member, overwrites)
            return await guild.create_text_channel(
                name=CHANNEL_WELCOME_SINK,
                overwrites=safe,
                reason="The Network guild init",
            )

        sink = await _run_init_step(result, f"create #{CHANNEL_WELCOME_SINK}", _create)
        if sink is not None:
            result.created_channels.append(f"#{CHANNEL_WELCOME_SINK} (hidden)")
    else:
        await _edit_overwrites(
            bot_member,
            sink,
            overwrites,
            result=result,
            step=f"sync #{CHANNEL_WELCOME_SINK} permissions",
        )

    if sink is not None and sink.position != 0:

        async def _move_top() -> None:
            await sink.edit(position=0, reason="The Network guild init")

        moved = await _run_init_step(result, f"move #{CHANNEL_WELCOME_SINK} to top", _move_top)
        if moved is not None:
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
        label = f"#{channel.name}" if hasattr(channel, "name") else str(channel.id)
        if await _edit_overwrites(
            bot_member,
            channel,
            overwrites,
            result=result,
            step=f"sync subscribe announcement {label}",
        ):
            result.notes.append(f"Synced public subscribe permissions on {label}")


async def _sync_hub_public_channels(
    guild: discord.Guild,
    bot_member: discord.Member,
    network_category: discord.CategoryChannel,
    overwrites: dict,
    *,
    result: GuildInitResult,
) -> None:
    rules_channel_id = (
        guild.rules_channel.id
        if isinstance(guild.rules_channel, discord.TextChannel)
        else None
    )
    for channel in network_category.channels:
        if not isinstance(channel, discord.TextChannel):
            continue
        if rules_channel_id is not None and channel.id == rules_channel_id:
            continue
        if await _edit_overwrites(
            bot_member,
            channel,
            overwrites,
            result=result,
            step=f"sync hub channel #{channel.name}",
        ):
            result.notes.append(f"Synced hub permissions on #{channel.name}")


async def _sync_partner_feed_channels(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    profiles: list[ServerProfile],
    *,
    result: GuildInitResult,
) -> None:
    profiles_by_source = {
        profile.source_channel_id: profile
        for profile in profiles
        if profile.guild_id == guild.id and profile.partner_role_id is not None
    }
    if not profiles_by_source:
        return

    for category in guild.categories:
        if not category.name.casefold().endswith(" feed"):
            continue
        for channel in category.channels:
            if not isinstance(channel, discord.TextChannel):
                continue
            profile = profiles_by_source.get(channel.id)
            if profile is None:
                continue
            server_role = guild.get_role(profile.partner_role_id)  # type: ignore[arg-type]
            if server_role is None:
                result.notes.append(
                    f"Skipped #{channel.name}: partner role {profile.partner_role_id} missing"
                )
                continue
            overwrites = dict(
                build_server_feed_channel_overwrites(
                    guild,
                    bot_member,
                    server_role,
                    access_role,
                    human_moderator_role,
                )
            )
            label = f"partner feed #{channel.name} ({server_role.name})"
            if await _edit_overwrites(
                bot_member,
                channel,
                overwrites,
                result=result,
                step=f"sync {label}",
            ):
                result.notes.append(f"Synced partner follow permissions on {label}")
            if channel.type is not discord.ChannelType.news:
                result.notes.append(
                    f"#{channel.name} is not an announcement channel — recreate the server "
                    "feed or convert it manually so Channel Follow can find it."
                )


async def initialize_guild(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    access_role_name: str,
    moderator_role_name: str,
    profiles: list[ServerProfile] | None = None,
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
        await _ensure_moderator_role(
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
            dict(
                build_subscribe_category_overwrites(
                    guild, bot_member, access_role, human_moderator_role
                )
            ),
            result=result,
        )
        network_cat = await _ensure_category(
            guild,
            bot_member,
            CATEGORY_NETWORK,
            dict(
                build_hub_public_category_overwrites(
                    guild,
                    bot_member,
                    access_role,
                    human_moderator_role,
                    for_category=True,
                )
            ),
            result=result,
        )
        moderation = await _ensure_category(
            guild,
            bot_member,
            CATEGORY_MODERATION,
            dict(
                build_moderation_staff_overwrites(
                    guild, bot_member, human_moderator_role, for_category=True
                )
            ),
            result=result,
        )

        if network_cat is None:
            result.success = False
            result.reason = (
                "Could not create or sync **The Network** category. "
                "Check the bot role has **Manage Channels** and sits above partner roles."
            )
            return result

        rules_overwrites = dict(
            build_hub_public_category_overwrites(
                guild, bot_member, access_role, human_moderator_role
            )
        )
        await _move_rules_channel(
            guild, bot_member, network_cat, rules_overwrites, result=result
        )
        await _sync_hub_public_channels(
            guild, bot_member, network_cat, rules_overwrites, result=result
        )

        mod_only_overwrites = dict(
            build_moderation_staff_overwrites(guild, bot_member, human_moderator_role)
        )
        if moderation is not None:
            mod_only_source = await _find_moderator_only_channel(guild)
            if mod_only_source is not None and mod_only_source.category_id != moderation.id:
                if await _edit_overwrites(
                    bot_member,
                    mod_only_source,
                    mod_only_overwrites,
                    result=result,
                    step=f"move moderator-only channel #{mod_only_source.name}",
                    category=moderation,
                    name=CHANNEL_MODERATOR_ONLY,
                ):
                    result.moved_channels.append(
                        f"{mod_only_source.mention} → "
                        f"{CATEGORY_MODERATION}/{CHANNEL_MODERATOR_ONLY}"
                    )
            else:
                await _ensure_text_channel(
                    guild,
                    bot_member,
                    name=CHANNEL_MODERATOR_ONLY,
                    category=moderation,
                    overwrites=mod_only_overwrites,
                    topic="Moderator discussion",
                    result=result,
                )

            await _ensure_text_channel(
                guild,
                bot_member,
                name=CHANNEL_JOIN_REQUESTS,
                category=moderation,
                overwrites=mod_only_overwrites,
                topic="Pending partner join requests",
                result=result,
            )
            await _ensure_text_channel(
                guild,
                bot_member,
                name=CHANNEL_COMMANDS,
                category=moderation,
                overwrites=dict(
                    build_commands_channel_overwrites(guild, bot_member, human_moderator_role)
                ),
                topic="Run The Network bot commands here",
                result=result,
            )

        managed_category_ids = {
            category.id
            for category in (subscribe, network_cat, moderation)
            if category is not None
        }
        for category in guild.categories:
            if category.id in managed_category_ids:
                continue
            if category.name.casefold().endswith(" feed"):
                if await _edit_overwrites(
                    bot_member,
                    category,
                    dict(
                        build_subscribe_category_overwrites(
                            guild, bot_member, access_role, human_moderator_role
                        )
                    ),
                    result=result,
                    step=f"sync feed category {category.name}",
                ):
                    result.notes.append(
                        f"Synced permissions on feed category {category.name}"
                    )

        await _ensure_welcome_sink_channel(guild, bot_member, result=result)

        if subscribe is not None:
            await _sync_subscribe_announcement_channels(
                guild,
                bot_member,
                subscribe,
                access_role,
                human_moderator_role,
                result=result,
            )

        if profiles:
            await _sync_partner_feed_channels(
                guild,
                bot_member,
                access_role,
                human_moderator_role,
                profiles,
                result=result,
            )

        result.notes.append(
            f"Place network announcement outputs in **{CATEGORY_SUBSCRIBE}**. "
            f"Partner feeds are created under each network's feed category."
        )
        if result.failed_steps:
            result.notes.insert(
                0,
                f"Init completed with {len(result.failed_steps)} permission sync warning(s). "
                "See notes below for each step.",
            )
    except NetworkValidationError as exc:
        return GuildInitResult(success=False, reason=str(exc))

    return result
