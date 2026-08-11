from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from bot.app.layout import ApplyMode, LayoutContext, apply_layout, compile_hub
from bot.app.layout.compiler import ResourceKind
from bot.app.layout.managed import hub_channel_name
from bot.app.recipes.registry import RecipeRegistry, recipe
from bot.core.models.client import Client
from bot.core.models.errors import NetworkValidationError
from bot.core.networks.roles import (
    ensure_bot_access_role,
    resolve_access_role_by_name,
    resolve_operator_role_by_name,
    validate_hub_permissions,
)
from bot.core.views import ViewRegistry
from bot.features.channels.resolve import (
    HUB_CHANNEL_ADMIN,
    resolve_human_moderator_role,
)
from bot.features.recipes.hub.reconcilers import (
    _ensure_human_moderator_role,
    _run_init_step,
    _sync_hub_notification_defaults,
)
from bot.features.recipes.hub.result import GuildInitResult

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot
    from bot.app.context import BotContext
    from bot.app.recipes.runtime import RecipeContext

logger = logging.getLogger(__name__)

__all__ = [
    "GuildInitResult",
    "initialize_guild",
    "_ensure_human_moderator_role",
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


async def _compose_lifecycle_recipe(
    recipe_context: RecipeContext | None,
    bot: NetworkRelayBot | None,
    name: str,
    *,
    core: BotContext | None = None,
    **inputs: Any,
) -> Any:
    """Prefer ``run()``; body helpers only when no recipe context/registry exists."""
    if recipe_context is not None:
        return await recipe_context.run(name, **inputs)
    registry = getattr(bot, "recipe_registry", None) if bot is not None else None
    if isinstance(registry, RecipeRegistry):
        return await registry.run(name, **inputs)
    return await _lifecycle_body(name, core=core, bot=bot, **inputs)


async def _lifecycle_body(
    name: str,
    *,
    core: BotContext | None,
    bot: NetworkRelayBot | None,
    **inputs: Any,
) -> Any:
    """Direct-call fallback for unit/live callers that bypass the recipe registry."""
    if name == "hub.migrate":
        from bot.features.recipes.hub.migrate import migrate_hub_layout

        return await migrate_hub_layout(
            inputs["guild"],
            inputs["layout_context"],
            context=core,
            clients=inputs.get("clients"),
            interaction=inputs.get("interaction"),
        )
    if name == "hub.ensure_installs":
        from bot.features.recipes.hub.installs import ensure_hub_installs

        if core is None:
            return None
        pass_result = await ensure_hub_installs(
            inputs["guild"],
            inputs["bot_member"],
            context=core,
            bot=bot,
            view_registry=inputs.get("view_registry"),
            bound_ids=inputs.get("bound_ids"),
        )
        result = inputs.get("result")
        if result is not None:
            result.notes.extend(pass_result.notes)
            result.failed_steps.extend(pass_result.failed_steps)
        return pass_result
    if name == "clients.reconnect":
        from bot.features.recipes.hub.clients.reconnect import reconnect_clients_on_init

        if bot is None or core is None:
            return None
        await reconnect_clients_on_init(
            inputs["guild"],
            bot,
            core,
            inputs["bot_member"],
            inputs["access_role"],
            inputs["human_moderator_role"],
            list(inputs.get("clients") or []),
            result=inputs["result"],
            view_registry=inputs["view_registry"],
        )
        return None
    raise RuntimeError(f"No lifecycle fallback for recipe {name!r}")


@recipe("hub.initialize")
async def initialize_guild_recipe(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    interaction: discord.Interaction | None = None,
    view_registry: ViewRegistry | None = None,
) -> GuildInitResult:
    from bot.app.widgets import PersistentViewRegistry

    registry = view_registry or PersistentViewRegistry(recipe_context.bot)
    return await initialize_guild(
        guild,
        bot_member,
        access_role_name=recipe_context.bot.settings.network_access_role_name,
        operator_role_name=recipe_context.bot.settings.network_operator_role_name,
        clients=await recipe_context.core.store.clients.list_all(),
        bot=recipe_context.bot,
        context=recipe_context.core,
        view_registry=registry,
        interaction=interaction,
        recipe_context=recipe_context,
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
    view_registry: ViewRegistry | None = None,
    interaction: discord.Interaction | None = None,
    recipe_context: RecipeContext | None = None,
) -> GuildInitResult:
    result = GuildInitResult(success=True)

    try:
        access_role = resolve_access_role_by_name(guild, role_name=access_role_name)
        operator_role = resolve_operator_role_by_name(guild, role_name=operator_role_name)
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
        result.updated_roles.append(f"Using access role {access_role.name}")
        result.updated_roles.append(f"Using operator role {operator_role.name}")

        human_moderator_role = await _ensure_human_moderator_role(guild, bot_member, result=result)

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
        migration = await _compose_lifecycle_recipe(
            recipe_context,
            bot,
            "hub.migrate",
            core=context,
            guild=guild,
            layout_context=layout_ctx,
            interaction=interaction,
            clients=list(clients or []),
        )
        if not migration.success:
            result.success = False
            result.reason = migration.reason or "Hub migration did not complete."
            result.notes.extend(migration.notes)
            return result
        bound_ids = dict(migration.bound_ids)
        result.notes.extend(migration.notes)
        result.rectifications.extend(
            note for note in migration.notes if note.startswith("Migrated ")
        )

        hub_resources = compile_hub(layout_ctx)
        hub_batch = await apply_layout(
            layout_ctx,
            hub_resources,
            mode=ApplyMode.ENSURE,
            bound_ids=bound_ids,
        )
        for item in hub_batch.results:
            if not item.success:
                result.failed_steps.append(f"layout {item.resource_id}: {item.detail or 'failed'}")
            elif item.changed and item.channel is not None:
                result.rectifications.append(
                    f"Synced layout resource `{item.resource_id}` ({item.channel.mention})."
                )

        hub_category_ids = {
            resource.id
            for resource in hub_resources
            if resource.kind is ResourceKind.CATEGORY
        }
        missing_hub_categories = [
            item
            for item in hub_batch.results
            if item.resource_id in hub_category_ids
            and not isinstance(item.channel, discord.CategoryChannel)
        ]
        if missing_hub_categories:
            result.success = False
            result.reason = (
                "Could not create or sync hub layout. "
                "Check the bot role has **Manage Channels**."
            )
            if hub_batch.failures:
                result.notes.extend(hub_batch.failures)
            return result

        for item in hub_batch.results:
            if item.channel is not None:
                bound_ids[item.resource_id] = item.channel.id

        if recipe_context is not None or context is not None:
            await _compose_lifecycle_recipe(
                recipe_context,
                bot,
                "hub.ensure_installs",
                core=context,
                guild=guild,
                bot_member=bot_member,
                bound_ids=bound_ids,
                view_registry=view_registry,
                result=result,
            )

        if bot is not None and context is not None and view_registry is not None:
            await _compose_lifecycle_recipe(
                recipe_context,
                bot,
                "clients.reconnect",
                core=context,
                guild=guild,
                bot_member=bot_member,
                access_role=access_role,
                human_moderator_role=human_moderator_role,
                clients=list(clients or []),
                result=result,
                view_registry=view_registry,
            )
            await context.refresh_projections()

        await _sync_hub_notification_defaults(
            guild,
            bot_member,
            result=result,
            step="refresh server notification defaults",
        )

        admin_channel_name = hub_channel_name(HUB_CHANNEL_ADMIN)
        result.notes.append(
            f"Hub ready. Use **#{admin_channel_name}** under Moderation to create networks; "
            "clients subscribe from their **client-profile** channel."
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
            reason=(f"Unexpected error during server init:\n• **{type(exc).__name__}**: {exc}"),
        )

    return result
