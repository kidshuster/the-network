from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.domain.client import Client
from bot.domain.errors import NetworkValidationError
from bot.services.guild_init_reconcilers import (
    _edit_overwrites,
    _ensure_announcement_channel,
    _ensure_category,
    _ensure_human_moderator_role,
    _ensure_text_channel,
    _find_moderator_only_channel,
    _move_rules_channel,
    _reorder_guild_categories,
    _reorder_hub_categories,
    _reorder_moderation_channels,
    _run_init_step,
    _sync_client_categories,
    _sync_hub_notification_defaults,
    _sync_hub_public_channels,
)
from bot.services.guild_init_result import GuildInitResult
from bot.services.guild_layout import (
    CATEGORY_MODERATION,
    CATEGORY_NETWORK,
    CHANNEL_COMMANDS,
    CHANNEL_JOIN_REQUESTS,
    CHANNEL_JOIN_THE_NETWORK,
    CHANNEL_MODERATOR_ONLY,
    resolve_human_moderator_role,
    resolve_join_the_network_channel,
    resolve_leaders_category,
)
from bot.services.guild_permissions import (
    build_hub_public_category_overwrites,
    build_moderation_staff_overwrites,
)
from bot.services.network_provision import (
    resolve_access_role_by_name,
    resolve_operator_role_by_name,
    validate_hub_permissions,
)
from bot.services.view_registry import ViewRegistry
from bot.smoke.provision_flow import run_guild_init_smoke_checks, run_post_init_join_smoke

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

__all__ = [
    "GuildInitResult",
    "initialize_guild",
    "_edit_overwrites",
    "_ensure_announcement_channel",
    "_ensure_human_moderator_role",
    "_reorder_guild_categories",
    "_reorder_hub_categories",
    "_run_init_step",
]

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
    view_registry: ViewRegistry | None = None,
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
            from bot.services.changelog import sync_changelog_releases
            from bot.services.leaders_channel import ensure_leaders_channels

            leaders, changelog, leaders_sync = await ensure_leaders_channels(
                guild,
                bot_member,
                context,
                access_role=access_role,
                human_moderator_role=human_moderator_role,
                operator_role=operator_role,
            )
            result.rectifications.extend(leaders_sync.rectification_notes())
            result.rectification_skipped.extend(leaders_sync.skip_notes())
            result.rectification_failures.extend(leaders_sync.failures)
            if leaders is not None:
                result.notes.append(f"Leaders channel synced at {leaders.mention}.")
            if changelog is not None:
                posted = await sync_changelog_releases(context, changelog)
                if posted:
                    result.notes.append(
                        f"Posted {posted} changelog release(s) to {changelog.mention}."
                    )

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

        if bot is not None and context is not None and view_registry is not None:
            from bot.services.hub_announcements import ensure_hub_announcements_client

            await ensure_hub_announcements_client(
                guild,
                bot,
                context,
                result=result,
                view_registry=view_registry,
            )

        guild_clients = [
            client for client in (clients or []) if client.guild_id == guild.id
        ]
        if clients and bot is not None and context is not None and view_registry is not None:
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
                view_registry=view_registry,
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

        if bot is not None and context is not None and view_registry is not None:
            from bot.services.join_requests_sticky import sync_hub_join_sticky
            from bot.services.rules_sticky import sync_rules_sticky

            join_channel = resolve_join_the_network_channel(guild)
            if join_channel is not None:
                join_view = view_registry.register_join_network_view()
                join_result = await sync_hub_join_sticky(
                    guild,
                    bot_member,
                    join_channel,
                    join_view,
                    get_setting=context.settings_repo.get,
                    set_setting=context.settings_repo.set,
                    wipe_channel=True,
                )
                if join_result.message is not None:
                    result.notes.append(
                        f"Join guide synced in {join_channel.mention}."
                    )

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
                admin_view = view_registry.register_network_admin_view()
                admin_result = await sync_network_admin_sticky(
                    guild,
                    bot_member,
                    admin_channel,
                    context,
                    admin_view,
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
