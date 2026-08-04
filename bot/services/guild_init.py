from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from bot.constants import LEGACY_MODERATOR_ROLE_NAME
from bot.domain.errors import NetworkValidationError
from bot.domain.client import Client
from bot.services.guild_layout import (
    CATEGORY_MODERATION,
    CATEGORY_NETWORK,
    CHANNEL_COMMANDS,
    CHANNEL_JOIN_REQUESTS,
    CHANNEL_JOIN_THE_NETWORK,
    CHANNEL_LEADERS,
    CHANNEL_MODERATOR_ONLY,
    CHANNEL_RULES,
    LEGACY_CHANNEL_LEADERS,
    resolve_category,
    resolve_human_moderator_role,
    resolve_join_the_network_channel,
    resolve_leaders_category,
)
from bot.services.guild_permissions import (
    build_hub_public_category_overwrites,
    build_moderation_staff_overwrites,
    filter_configurable_overwrites,
    sync_client_category_permissions,
)
from bot.services.network_provision import (
    resolve_access_role_by_name,
    resolve_operator_role_by_name,
    validate_hub_permissions,
)
from bot.smoke.provision_flow import run_guild_init_smoke_checks, run_post_init_join_smoke

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

_STEP_TIMEOUT_SECONDS = 45.0

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
        return await asyncio.wait_for(action(), timeout=_STEP_TIMEOUT_SECONDS)
    except TimeoutError:
        message = f"{step}: timed out after {_STEP_TIMEOUT_SECONDS:.0f}s"
        result.failed_steps.append(message)
        result.notes.append(f"Could not {step}: timed out")
        logger.warning("Guild init step timed out", extra={"step": step})
        return fallback
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
    sync_from_category: bool = False,
    **edit_kwargs: object,
) -> bool:
    is_channel = not isinstance(target, discord.CategoryChannel)
    safe_overwrites = filter_configurable_overwrites(
        bot_member,
        overwrites,
        for_channel=is_channel,
    )

    async def _edit() -> None:
        if sync_from_category and is_channel:
            await target.edit(
                sync_permissions=True,
                reason="The Network guild init",
                **edit_kwargs,  # type: ignore[arg-type]
            )
            return
        await target.edit(
            overwrites=safe_overwrites,
            reason="The Network guild init",
            **edit_kwargs,  # type: ignore[arg-type]
        )

    edited = await _run_init_step(result, step, _edit)
    if edited is not None or not (sync_from_category and is_channel):
        return edited is not None

    async def _sync_only() -> None:
        await target.edit(
            sync_permissions=True,
            reason="The Network guild init",
            **edit_kwargs,  # type: ignore[arg-type]
        )

    synced = await _run_init_step(result, f"{step} (inherit category)", _sync_only)
    return synced is not None


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
    sync_from_category: bool = False,
) -> discord.TextChannel | None:
    safe_overwrites = filter_configurable_overwrites(
        bot_member,
        overwrites,
        for_channel=True,
    )

    for channel in guild.text_channels:
        if channel.name.casefold() == name.casefold() and channel.category_id == category.id:
            await _edit_overwrites(
                bot_member,
                channel,
                overwrites,
                result=result,
                step=f"sync #{name} permissions",
                sync_from_category=sync_from_category,
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
                sync_from_category=sync_from_category,
                category=category,
                name=name,
                topic=topic,
            )
            if moved:
                result.moved_channels.append(f"#{name} → {category.name}")
            return channel

    async def _create() -> discord.TextChannel:
        if sync_from_category:
            return await guild.create_text_channel(
                name=name,
                category=category,
                topic=topic,
                reason="The Network guild init",
            )
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


async def _ensure_human_moderator_role(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    result: GuildInitResult,
) -> discord.Role | None:
    role = resolve_human_moderator_role(guild)
    if role is not None:
        if bot_member.top_role.position > role.position:
            needs_update = (
                role.permissions != _MODERATOR_GUILD_PERMISSIONS
                or not role.mentionable
            )

            if needs_update:
                async def _update() -> discord.Role:
                    await role.edit(
                        permissions=_MODERATOR_GUILD_PERMISSIONS,
                        mentionable=True,
                        reason="The Network guild init",
                    )
                    return role

                updated = await _run_init_step(
                    result, f"update {role.name} role permissions", _update
                )
                if updated is not None:
                    result.updated_roles.append(f"Updated {role.name}")
        elif not role.mentionable:
            result.notes.append(
                f"**{role.name}** is not mentionable and the bot cannot edit that role "
                "(role is above the bot). Join requests in "
                f"**#{CHANNEL_JOIN_REQUESTS}** will not ping moderators until "
                f"**{role.name}** is set to mentionable."
            )
        return role

    async def _create() -> discord.Role:
        return await guild.create_role(
            name=LEGACY_MODERATOR_ROLE_NAME,
            permissions=_MODERATOR_GUILD_PERMISSIONS,
            mentionable=True,
            hoist=True,
            reason="The Network guild init",
        )

    created = await _run_init_step(result, "create Moderator role", _create)
    if created is not None:
        result.updated_roles.append(f"Created {LEGACY_MODERATOR_ROLE_NAME}")
    return created


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
            sync_from_category=rules.category_id == network_category.id,
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


async def _sync_client_categories(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    clients: list[Client],
    *,
    result: GuildInitResult,
) -> None:
    clients_by_category = {client.category_id: client for client in clients if client.guild_id == guild.id}
    if not clients_by_category:
        return

    for category in guild.categories:
        client = clients_by_category.get(category.id)
        if client is None:
            continue
        client_role = guild.get_role(client.client_role_id)
        if client_role is None:
            result.notes.append(
                f"Skipped category {category.name}: client role missing"
            )
            continue

        async def _sync(
            cat: discord.CategoryChannel = category,
            role: discord.Role = client_role,
        ) -> None:
            await sync_client_category_permissions(
                cat,
                bot_member,
                role,
                access_role,
                human_moderator_role,
                reason="The Network server init",
            )

        if await _run_init_step(result, f"sync client category {category.name}", _sync):
            result.notes.append(f"Synced client category {category.name}")


async def _reorder_moderation_channels(
    moderation: discord.CategoryChannel,
    *,
    result: GuildInitResult,
) -> None:
    order = ["moderator-only", "join-requests", "commands"]
    channels = [
        ch for ch in moderation.channels if isinstance(ch, discord.TextChannel)
    ]
    by_name = {ch.name.casefold(): ch for ch in channels}
    for index, name in enumerate(order):
        channel = by_name.get(name)
        if channel is None:
            continue

        async def _move(ch: discord.TextChannel = channel, pos: int = index) -> None:
            await ch.edit(position=pos, reason="The Network server init")

        await _run_init_step(result, f"order #{name}", _move)


async def _reorder_guild_categories(
    moderation: discord.CategoryChannel,
    network_category: discord.CategoryChannel,
    *,
    leaders_category: discord.CategoryChannel | None = None,
    client_categories: list[discord.CategoryChannel] | None = None,
    result: GuildInitResult,
) -> None:
    """Hub order: Moderation, The Network, Leaders — then client categories."""
    ordered_hub = [moderation, network_category]
    if leaders_category is not None:
        ordered_hub.append(leaders_category)

    for index, category in enumerate(ordered_hub):

        async def _move(
            cat: discord.CategoryChannel = category,
            pos: int = index,
        ) -> None:
            await cat.edit(position=pos, reason="The Network server init")

        await _run_init_step(
            result,
            f"order hub category {category.name}",
            _move,
        )

    if not client_categories:
        return

    start = len(ordered_hub)
    for offset, category in enumerate(client_categories):
        pos = start + offset

        async def _move_client(
            cat: discord.CategoryChannel = category,
            position: int = pos,
        ) -> None:
            await cat.edit(position=position, reason="The Network server init")

        await _run_init_step(
            result,
            f"order client category {category.name}",
            _move_client,
        )


async def _reorder_hub_categories(
    moderation: discord.CategoryChannel,
    network_category: discord.CategoryChannel,
    *,
    result: GuildInitResult,
) -> None:
    await _reorder_guild_categories(
        moderation,
        network_category,
        result=result,
    )


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
        if channel.name.casefold() in {
            CHANNEL_LEADERS.casefold(),
            LEGACY_CHANNEL_LEADERS.casefold(),
        }:
            continue
        if await _edit_overwrites(
            bot_member,
            channel,
            overwrites,
            result=result,
            step=f"sync hub channel #{channel.name}",
            sync_from_category=True,
        ):
            result.notes.append(f"Synced hub permissions on #{channel.name}")


async def _sync_hub_notification_defaults(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    result: GuildInitResult,
    step: str,
) -> None:
    from bot.services.guild_notifications import sync_guild_notification_policy

    async def _run() -> None:
        await sync_guild_notification_policy(
            guild,
            bot_member,
            reason="The Network guild init",
            result=result,
        )

    await _run_init_step(result, step, _run)


async def initialize_guild(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    access_role_name: str,
    operator_role_name: str,
    clients: list[Client] | None = None,
    bot: NetworkRelayBot | None = None,
    context: BotContext | None = None,
    skip_join_smoke: bool = False,
) -> GuildInitResult:
    result = GuildInitResult(success=True)

    try:
        access_role = resolve_access_role_by_name(guild, role_name=access_role_name)
        operator_role = resolve_operator_role_by_name(
            guild, role_name=operator_role_name
        )
        human_moderator_role = resolve_human_moderator_role(guild)

        validate_hub_permissions(
            bot_member,
            access_role,
            operator_role=operator_role,
            operator_role_name=operator_role_name,
            human_moderator_role=human_moderator_role,
        )

        assert operator_role is not None
        smoke = await run_guild_init_smoke_checks(
            guild,
            bot_member,
            access_role,
            access_role_name=access_role_name,
            operator_role_name=operator_role_name,
        )
        result.updated_roles.append(f"Using access role {access_role.name}")
        result.updated_roles.append(f"Using operator role {operator_role.name}")
        result.notes.append(
            "Permission smoke passed: " + ", ".join(smoke.operator_steps) + "."
        )
        result.notes.append(
            "Provision smoke passed (Accept path): "
            + ", ".join(smoke.provision_steps)
            + "."
        )

        await _sync_hub_notification_defaults(
            guild,
            bot_member,
            result=result,
            step="set server notification defaults",
        )

        human_moderator_role = await _ensure_human_moderator_role(
            guild, bot_member, result=result
        )

        moderation = await _ensure_category(
            guild,
            bot_member,
            CATEGORY_MODERATION,
            dict(
                build_moderation_staff_overwrites(
                    guild,
                    bot_member,
                    human_moderator_role,
                    for_category=True,
                    allow_slash_commands=True,
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

        if network_cat is None or moderation is None:
            result.success = False
            result.reason = (
                "Could not create or sync hub categories. "
                "Check the bot role has **Manage Channels**."
            )
            return result

        await _reorder_hub_categories(moderation, network_cat, result=result)

        rules_overwrites = dict(
            build_hub_public_category_overwrites(
                guild, bot_member, access_role, human_moderator_role
            )
        )
        await _move_rules_channel(
            guild, bot_member, network_cat, rules_overwrites, result=result
        )

        hub_public = dict(
            build_hub_public_category_overwrites(
                guild, bot_member, access_role, human_moderator_role
            )
        )
        await _ensure_text_channel(
            guild,
            bot_member,
            name=CHANNEL_JOIN_THE_NETWORK,
            category=network_cat,
            overwrites=hub_public,
            topic="Join The Network hub as a client",
            result=result,
            sync_from_category=True,
        )
        await _sync_hub_public_channels(
            guild, bot_member, network_cat, hub_public, result=result
        )
        if context is not None:
            from bot.services.leaders_channel import ensure_leaders_channel

            leaders = await ensure_leaders_channel(
                guild,
                bot_member,
                context,
                access_role=access_role,
                human_moderator_role=human_moderator_role,
            )
            if leaders is not None:
                result.notes.append(f"Leaders channel synced at {leaders.mention}.")

        mod_only_overwrites = dict(
            build_moderation_staff_overwrites(guild, bot_member, human_moderator_role)
        )
        await _ensure_text_channel(
            guild,
            bot_member,
            name=CHANNEL_COMMANDS,
            category=moderation,
            overwrites=mod_only_overwrites,
            topic="Network administration",
            result=result,
            sync_from_category=True,
        )
        await _ensure_text_channel(
            guild,
            bot_member,
            name=CHANNEL_JOIN_REQUESTS,
            category=moderation,
            overwrites=mod_only_overwrites,
            topic="Pending client join requests",
            result=result,
            sync_from_category=True,
        )
        mod_only_source = await _find_moderator_only_channel(guild)
        if mod_only_source is not None and mod_only_source.category_id != moderation.id:
            if await _edit_overwrites(
                bot_member,
                mod_only_source,
                mod_only_overwrites,
                result=result,
                step=f"move moderator-only channel #{mod_only_source.name}",
                sync_from_category=True,
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
                sync_from_category=True,
            )

        await _reorder_moderation_channels(moderation, result=result)

        guild_clients = [
            client for client in (clients or []) if client.guild_id == guild.id
        ]
        if clients and bot is not None and context is not None:
            from bot.services.client_reconnect import reconnect_clients_on_init

            await reconnect_clients_on_init(
                guild,
                bot,
                context,
                bot_member,
                access_role,
                human_moderator_role,
                clients,
                result=result,
            )
            await context.client_cache.load_cache()
            await context.routing_service.load_cache()
        elif clients:
            await _sync_client_categories(
                guild,
                bot_member,
                access_role,
                human_moderator_role,
                clients,
                result=result,
            )

        client_categories: list[discord.CategoryChannel] = []
        for client in guild_clients:
            category = guild.get_channel(client.category_id)
            if isinstance(category, discord.CategoryChannel):
                client_categories.append(category)
        client_categories.sort(key=lambda cat: cat.name.casefold())

        await _reorder_guild_categories(
            moderation,
            network_cat,
            leaders_category=resolve_leaders_category(guild),
            client_categories=client_categories,
            result=result,
        )

        if bot is not None and context is not None:
            from bot.services.join_requests_sticky import sync_hub_join_sticky
            from bot.services.rules_sticky import sync_rules_sticky

            join_channel = resolve_join_the_network_channel(guild)
            if join_channel is not None:
                join_result = await sync_hub_join_sticky(
                    guild,
                    bot_member,
                    bot,
                    join_channel,
                    get_setting=context.settings_repo.get,
                    set_setting=context.settings_repo.set,
                    wipe_channel=True,
                )
                if join_result.message is not None:
                    result.notes.append(
                        f"Join guide synced in {join_channel.mention}."
                    )
                from bot.ui.join_views import JoinNetworkView

                bot.add_view(JoinNetworkView(bot))

            rules_result = await sync_rules_sticky(
                guild,
                bot_member,
                get_setting=context.settings_repo.get,
                set_setting=context.settings_repo.set,
            )
            if rules_result.message is not None:
                result.notes.append("Hub rules sticky synced.")

            from bot.services.guild_layout import resolve_network_admin_channel
            from bot.services.network_admin_sticky import sync_network_admin_sticky

            admin_channel = resolve_network_admin_channel(guild)
            if admin_channel is not None:
                admin_result = await sync_network_admin_sticky(
                    guild,
                    bot_member,
                    bot,
                    admin_channel,
                    context,
                    get_setting=context.settings_repo.get,
                    set_setting=context.settings_repo.set,
                    wipe_channel=True,
                )
                if admin_result.message is not None:
                    result.notes.append(
                        f"Network admin panel synced in {admin_channel.mention}."
                    )
                elif admin_result.reason:
                    result.failed_steps.append(
                        f"Network admin sticky: {admin_result.reason}"
                    )

                from bot.ui.network_admin_views import NetworkAdminView

                bot.add_view(NetworkAdminView(bot))

            try:
                if not skip_join_smoke:
                    smoke_note = await run_post_init_join_smoke(guild, bot, context)
                    from bot.smoke.provision_flow import cleanup_join_requests_smoke_artifacts

                    await cleanup_join_requests_smoke_artifacts(guild, context, bot_member)
                else:
                    smoke_note = None
            except NetworkValidationError:
                raise
            except RuntimeError as exc:
                raise NetworkValidationError(
                    "Join-approval smoke failed:\n"
                    f"• {exc}\n\n"
                    "Fix permissions or probe failures, then run `/server init` again."
                ) from exc
            if smoke_note is not None:
                result.notes.append(smoke_note)

        await _sync_hub_notification_defaults(
            guild,
            bot_member,
            result=result,
            step="refresh server notification defaults",
        )

        result.notes.append(
            "Hub ready. Use **#commands** under Moderation to create networks; "
            "clients subscribe from their **network-profile** channel."
        )
        if result.failed_steps:
            result.notes.insert(
                0,
                f"Init completed with {len(result.failed_steps)} permission sync warning(s). "
                "See notes below for each step.",
            )
    except NetworkValidationError as exc:
        return GuildInitResult(success=False, reason=str(exc))
    except Exception as exc:
        logger.exception("Guild init failed unexpectedly")
        return GuildInitResult(
            success=False,
            reason=(
                "Unexpected error during server init:\n"
                f"• **{type(exc).__name__}**: {exc}"
            ),
        )

    return result
