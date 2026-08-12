"""Client lifecycle recipes (provision-from-request entry)."""

from __future__ import annotations

from typing import Any

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.contracts.widgets import (
    OpenEphemeralView,
    OpenModal,
    SelectOptionSpec,
    SelectSpec,
    recipe_handler,
)
from bot.core.templates import render_text
from bot.core.text import truncate_external_text
from bot.errors import UserFacingError
from bot.features.widgets.guards import (
    interaction_actor,
    interaction_bot_member,
    interaction_guild,
    interaction_view_registry,
    require_client_member,
    require_manage_guild,
)


@recipe("client.provision_from_request")
async def provision_client_from_request(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    request: Any,
    image: Any,
    view_registry: Any,
) -> Any:
    from bot.core.media.emoji import EmojiService, emoji_sync_target_from_client
    from bot.features.recipes.hub.clients.profile_post import build_client_profile_embed
    from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message
    from bot.features.recipes.hub.clients.provision import provision_client
    from bot.features.recipes.hub.clients.reconcile import reconcile_client_from_request
    from bot.features.recipes.hub.onboarding.service import _ProvisionOutcome

    bot = recipe_context.bot
    core = recipe_context.core
    repair_client_id = getattr(request, "repair_client_id", None)
    if repair_client_id is not None:
        existing = await core.store.clients.get_by_id(int(repair_client_id))
        if existing is None:
            return _ProvisionOutcome(
                success=False,
                error="Repair target client was not found.",
            )
        _client, role, profile = await reconcile_client_from_request(
            guild,
            bot_member,
            bot=bot,
            context=core,
            request=request,
            client=existing,
            image=image,
            view_registry=view_registry,
            access_role_name=bot.settings.network_access_role_name,
            operator_role_name=bot.settings.network_operator_role_name,
        )
        return _ProvisionOutcome(
            success=True,
            client_role=role,
            profile_channel=profile,
        )

    provision = await provision_client(
        guild,
        bot_member,
        server_name=request.server_name,
        access_role_name=bot.settings.network_access_role_name,
        operator_role_name=bot.settings.network_operator_role_name,
    )
    network_keys = [network.key for network in await core.store.networks.list_all()]
    starter = await provision.profile_channel.send(
        embed=build_client_profile_embed(
            server_name=request.server_name,
            display_name=request.display_name,
            enabled=True,
        ),
        view=view_registry.register_client_profile_view(0, network_keys),
        silent=True,
    )
    client = await core.store.clients.create(
        guild_id=guild.id,
        server_name=request.server_name,
        display_name=request.display_name,
        category_id=provision.category.id,
        client_role_id=provision.client_role.id,
        profile_channel_id=provision.profile_channel.id,
        profile_message_id=starter.id,
    )
    await starter.edit(view=view_registry.register_client_profile_for_client(client, network_keys))
    emoji = await EmojiService().sync_for_profile(
        guild,
        emoji_sync_target_from_client(client, source_channel_id=provision.profile_channel.id),
        image,
        previous_hash=None,
        previous_emoji_id=None,
        force=True,
    )
    if emoji.emoji_id is not None:
        await core.store.clients.update_emoji_fields(
            client.id,
            emoji_id=emoji.emoji_id,
            emoji_name=emoji.emoji_name,
            image_hash=emoji.image_hash,
            degraded_reason=emoji.degraded_reason,
        )
        client = await core.store.clients.get_by_id(client.id) or client
    await refresh_client_profile_message(bot, core, guild, client, view_registry=view_registry)
    return _ProvisionOutcome(
        success=True,
        client_role=provision.client_role,
        profile_channel=provision.profile_channel,
    )


async def _require_client(recipe_context: RecipeContext, client_id: int) -> Any:
    if recipe_context.core is None:
        raise UserFacingError(render_text("bot_not_ready"), code="bot_not_ready")
    client = await recipe_context.core.store.clients.get_by_id(client_id)
    if client is None:
        raise UserFacingError(render_text("client_not_found"), code="client_not_found")
    return client


@recipe("client.edit.open")
async def open_client_edit(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    client_id: int,
) -> OpenModal:
    guild = interaction_guild(recipe_context.bot, interaction)
    member = interaction_actor(interaction)
    client = await _require_client(recipe_context, client_id)
    require_client_member(
        guild,
        member,
        client,
        popup="client_role_required_edit",
        allow_non_member=True,
    )
    return OpenModal(
        template_id="edit_client_profile",
        submit=recipe_handler("client.edit_profile", client_id=client_id),
        defaults={"display_name": client.display_name},
    )


@recipe("client.delete.confirm")
async def open_client_delete_confirm(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    client_id: int,
) -> OpenEphemeralView:
    guild = interaction_guild(recipe_context.bot, interaction)
    member = interaction_actor(interaction)
    client = await _require_client(recipe_context, client_id)
    require_client_member(
        guild,
        member,
        client,
        popup="client_role_required_delete",
        allow_non_member=True,
    )
    return OpenEphemeralView(
        template_id="delete_client_confirm",
        content=render_text("delete_client_confirm_prompt", server_name=client.server_name),
        bindings={
            "confirm_button": recipe_handler("client.delete", client_id=client_id),
            "cancel_button": recipe_handler("ui.dismiss"),
        },
    )


@recipe("client.delete")
async def delete_client(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    client_id: int,
) -> Any:
    from bot.features.recipes.hub.clients.deletion import delete_client_resources

    guild = interaction_guild(recipe_context.bot, interaction)
    member = interaction_actor(interaction)
    client = await _require_client(recipe_context, client_id)
    require_client_member(
        guild, member, client, popup="client_role_required_delete", allow_non_member=True
    )
    return await delete_client_resources(
        guild,
        interaction_bot_member(guild),
        client=client,
        client_repo=recipe_context.core.store.clients,
        network_repo=recipe_context.core.store.networks,
        context=recipe_context.core,
    )


@recipe("client.edit_profile")
async def edit_client_profile(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    client_id: int,
    display_name: str,
    profile_image: discord.Attachment | None = None,
) -> Any:
    from bot.features.recipes.hub.clients.profile_edit import apply_client_profile_edit

    guild = interaction_guild(recipe_context.bot, interaction)
    member = interaction_actor(interaction)
    client = await _require_client(recipe_context, client_id)
    require_client_member(
        guild, member, client, popup="client_role_required_edit", allow_non_member=True
    )
    return await apply_client_profile_edit(
        recipe_context.bot,
        recipe_context.core,
        guild,
        client_id=client_id,
        display_name=display_name,
        profile_image=profile_image,
        view_registry=interaction_view_registry(interaction),
    )


@recipe("client.toggle_timecode")
async def toggle_client_timecode(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    client_id: int,
) -> Any:
    from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message

    guild = interaction_guild(recipe_context.bot, interaction)
    member = interaction_actor(interaction)
    client = await _require_client(recipe_context, client_id)
    require_client_member(
        guild, member, client, popup="client_role_required_edit", allow_non_member=True
    )
    updated = await recipe_context.core.store.clients.set_timecode_enabled(
        client.id,
        not client.timecode_enabled,
    )
    await recipe_context.core.refresh_client_counts()
    await refresh_client_profile_message(
        recipe_context.bot,
        recipe_context.core,
        guild,
        updated,
        view_registry=interaction_view_registry(interaction),
    )
    return updated

@recipe("admin.client.delete.open")
async def open_admin_client_delete(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
) -> OpenEphemeralView:
    interaction_guild(recipe_context.bot, interaction)
    require_manage_guild(interaction_actor(interaction))
    clients = await recipe_context.core.store.clients.list_all()
    guild_id = recipe_context.bot.settings.guild_id
    options = [
        SelectOptionSpec(
            label=truncate_external_text(client.server_name, limit=100),
            value=str(client.id),
            description=truncate_external_text(client.display_name, limit=100),
        )
        for client in clients
        if client.guild_id == guild_id
    ][:25]
    if not options:
        raise UserFacingError(
            render_text("admin_no_clients_to_delete"),
            code="admin_no_clients_to_delete",
        )
    return OpenEphemeralView(
        template_id="admin_delete_client_select",
        content=render_text("admin_delete_client_select_prompt"),
        slots={
            "client_select": (
                SelectSpec(
                    tag="select",
                    placeholder="Select a client to delete…",
                    options=tuple(options),
                    handler=recipe_handler("admin.client.delete.prompt"),
                    min_values=1,
                    max_values=1,
                ),
            )
        },
    )


@recipe("admin.client.delete.prompt")
async def prompt_admin_client_delete(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    selected_client_ids: list[str] | tuple[str, ...] | set[str],
    select_values: list[str] | tuple[str, ...] | set[str] | None = None,
) -> OpenEphemeralView:
    del select_values
    interaction_guild(recipe_context.bot, interaction)
    require_manage_guild(interaction_actor(interaction))
    if not selected_client_ids:
        raise UserFacingError(
            render_text("admin_no_clients_to_delete"),
            code="admin_no_clients_to_delete",
        )
    client_id = int(next(iter(selected_client_ids)))
    client = await _require_client(recipe_context, client_id)
    return OpenEphemeralView(
        template_id="delete_client_confirm",
        content=render_text("delete_client_confirm_prompt", server_name=client.server_name),
        bindings={
            "confirm_button": recipe_handler("admin.client.delete", client_id=client_id),
            "cancel_button": recipe_handler("ui.dismiss"),
        },
    )


@recipe("admin.client.delete")
async def admin_delete_client(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    client_id: int,
) -> Any:
    from bot.features.recipes.hub.clients.deletion import delete_client_resources

    guild = interaction_guild(recipe_context.bot, interaction)
    require_manage_guild(interaction_actor(interaction))
    client = await _require_client(recipe_context, client_id)
    return await delete_client_resources(
        guild,
        interaction_bot_member(guild),
        client=client,
        client_repo=recipe_context.core.store.clients,
        network_repo=recipe_context.core.store.networks,
        context=recipe_context.core,
        force=True,
    )


@recipe("clients.rectify")
async def rectify_client(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    client: Any,
    result: Any,
    view_registry: Any,
) -> bool:
    from bot.features.recipes.hub.clients.reconnect import rectify_client_on_init

    return await rectify_client_on_init(
        guild,
        recipe_context.bot,
        recipe_context.core,
        bot_member,
        access_role,
        human_moderator_role,
        client,
        result=result,
        view_registry=view_registry,
    )


@recipe("clients.reconnect")
async def reconnect_clients(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    clients: list[Any],
    result: Any,
    view_registry: Any,
) -> None:
    from bot.features.recipes.hub.clients.reconnect import reconnect_clients_on_init

    await reconnect_clients_on_init(
        guild,
        recipe_context.bot,
        recipe_context.core,
        bot_member,
        access_role,
        human_moderator_role,
        clients,
        result=result,
        view_registry=view_registry,
    )
