from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.domain.client import Client
from bot.domain.errors import NetworkValidationError
from bot.hub.reconcilers import (
    _ensure_human_moderator_role,
    _reorder_guild_categories,
    _reorder_hub_categories,
    _run_init_step,
    _sync_hub_notification_defaults,
)
from bot.hub.resolve import (
    resolve_human_moderator_role,
    resolve_join_the_network_channel,
    resolve_leaders_category,
)
from bot.hub.result import GuildInitResult
from bot.layout import ApplyMode, LayoutContext, apply_layout, compile_client, compile_hub
from bot.networks.roles import (
    ensure_bot_access_role,
    resolve_access_role_by_name,
    resolve_operator_role_by_name,
    validate_hub_permissions,
)
from bot.smoke.provision_flow import run_guild_init_smoke_checks, run_post_init_join_smoke
from bot.ui.view_registry import ViewRegistry

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

__all__ = [
    "GuildInitResult",
    "initialize_guild",
    "_ensure_human_moderator_role",
    "_reorder_guild_categories",
    "_reorder_hub_categories",
    "_run_init_step",
]


def _layout_context(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    access_role: discord.Role,
    operator_role: discord.Role,
    bot_access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    client_roles: tuple[discord.Role, ...] = (),
) -> LayoutContext:
    return LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access_role,
        moderator_role=human_moderator_role,
        operator_role=operator_role,
        bot_access_role=bot_access_role,
        client_roles=client_roles,
        reason="The Network guild init",
    )


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
        if operator_role is None:
            validate_hub_permissions(
                bot_member,
                access_role,
                operator_role=None,
                operator_role_name=operator_role_name,
                human_moderator_role=None,
            )
            raise AssertionError("unreachable")
        bot_access_role = await ensure_bot_access_role(
            guild,
            bot_member,
            reason="The Network guild init",
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

        client_roles: list[discord.Role] = []
        for client in clients or []:
            if client.guild_id != guild.id:
                continue
            role = guild.get_role(client.client_role_id)
            if role is not None:
                client_roles.append(role)

        layout_ctx = _layout_context(
            guild,
            bot_member,
            access_role=access_role,
            operator_role=operator_role,
            bot_access_role=bot_access_role,
            human_moderator_role=human_moderator_role,
            client_roles=tuple(client_roles),
        )
        hub_batch = await apply_layout(
            layout_ctx,
            compile_hub(layout_ctx),
            mode=ApplyMode.ENSURE,
        )
        for item in hub_batch.results:
            if not item.success:
                result.failed_steps.append(
                    f"layout {item.resource_id}: {item.detail or 'failed'}"
                )
            elif item.changed and item.channel is not None:
                result.rectifications.append(
                    f"Synced layout resource `{item.resource_id}` ({item.channel.mention})."
                )

        moderation = hub_batch.resource("moderation")
        network_cat = hub_batch.resource("network")
        if not isinstance(moderation, discord.CategoryChannel) or not isinstance(
            network_cat,
            discord.CategoryChannel,
        ):
            result.success = False
            result.reason = (
                "Could not create or sync hub categories. "
                "Check the bot role has **Manage Channels**."
            )
            return result

        leaders_channel = hub_batch.resource("leaders_channel")
        changelog_channel = hub_batch.resource("changelog")
        if isinstance(leaders_channel, discord.TextChannel):
            result.notes.append(f"Leaders channel synced at {leaders_channel.mention}.")
        if context is not None and isinstance(changelog_channel, discord.TextChannel):
            from bot.hub.changelog import sync_changelog_releases

            posted = await sync_changelog_releases(context, changelog_channel)
            if posted:
                result.notes.append(
                    f"Posted {posted} changelog release(s) to {changelog_channel.mention}."
                )
            if context is not None:
                from bot.hub.leaders import (
                    CHANGELOG_CHANNEL_SETTINGS_KEY,
                    LEADERS_CHANNEL_SETTINGS_KEY,
                )

                if isinstance(leaders_channel, discord.TextChannel):
                    await context.store.settings.set(
                        LEADERS_CHANNEL_SETTINGS_KEY,
                        str(leaders_channel.id),
                    )
                if isinstance(changelog_channel, discord.TextChannel):
                    await context.store.settings.set(
                        CHANGELOG_CHANNEL_SETTINGS_KEY,
                        str(changelog_channel.id),
                    )

        if bot is not None and context is not None and view_registry is not None:
            from bot.hub.announcements import ensure_hub_announcements_client

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
            from bot.clients.reconnect import reconnect_clients_on_init

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
            from bot.clients.names import slugify_client_name

            for client in guild_clients:
                role = guild.get_role(client.client_role_id)
                if role is None:
                    result.notes.append(
                        f"Skipped client {client.server_name}: role missing"
                    )
                    continue
                client_ctx = LayoutContext(
                    guild=guild,
                    bot_member=bot_member,
                    access_role=access_role,
                    moderator_role=human_moderator_role,
                    operator_role=operator_role,
                    client_role=role,
                    server_name=client.server_name,
                    slug=slugify_client_name(client.server_name),
                    reason="The Network server init",
                )
                subs = []
                if context is not None:
                    subs = await context.store.clients.list_subscriptions_by_client(client.id)
                # reconcile category+profile; subscription channels when keys known
                batch = await apply_layout(
                    client_ctx,
                    compile_client(client_ctx),
                    mode=ApplyMode.RECONCILE_ONLY,
                )
                for item in batch.results:
                    if item.success and item.resource_id == "client":
                        result.rectifications.append(
                            f"**{client.server_name}**: rectified category permissions."
                        )
                    elif not item.success:
                        result.failed_steps.append(
                            f"sync client category {client.server_name}: {item.detail}"
                        )
                for subscription in subs:
                    if context is None:
                        break
                    network_id = subscription.network_id
                    if network_id is None:
                        continue
                    network = await context.store.networks.get_by_id(network_id)
                    if network is None:
                        continue
                    sub_ctx = LayoutContext(
                        guild=guild,
                        bot_member=bot_member,
                        access_role=access_role,
                        moderator_role=human_moderator_role,
                        operator_role=operator_role,
                        client_role=role,
                        server_name=client.server_name,
                        slug=slugify_client_name(client.server_name),
                        network_key=network.key,
                        reason="The Network server init",
                    )
                    await apply_layout(
                        sub_ctx,
                        compile_client(
                            sub_ctx,
                            include_subscribed=True,
                            channel_ids={"publish", "subscribe"},
                        ),
                        mode=ApplyMode.RECONCILE_ONLY,
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
            from bot.stickies.join_requests_sticky import sync_hub_join_sticky
            from bot.stickies.rules_sticky import sync_rules_sticky

            join_channel = resolve_join_the_network_channel(guild)
            if join_channel is not None:
                join_view = view_registry.register_join_network_view()
                join_result = await sync_hub_join_sticky(
                    guild,
                    bot_member,
                    join_channel,
                    join_view,
                    get_setting=context.store.settings.get,
                    set_setting=context.store.settings.set,
                    wipe_channel=True,
                )
                if join_result.message is not None:
                    result.notes.append(
                        f"Join guide synced in {join_channel.mention}."
                    )

            rules_result = await sync_rules_sticky(
                guild,
                bot_member,
                get_setting=context.store.settings.get,
                set_setting=context.store.settings.set,
            )
            if rules_result.message is not None:
                result.notes.append("Hub rules sticky synced.")

            from bot.hub.resolve import resolve_network_admin_channel
            from bot.stickies.network_admin_sticky import sync_network_admin_sticky

            admin_channel = resolve_network_admin_channel(guild)
            if admin_channel is not None:
                admin_view = view_registry.register_network_admin_view()
                admin_result = await sync_network_admin_sticky(
                    guild,
                    bot_member,
                    admin_channel,
                    context,
                    admin_view,
                    get_setting=context.store.settings.get,
                    set_setting=context.store.settings.set,
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
