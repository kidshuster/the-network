"""Client lifecycle recipes (provision-from-request entry)."""

from __future__ import annotations

from typing import Any

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.contracts.widgets import OpenEphemeralView, OpenModal, recipe_handler
from bot.core.templates import render_text
from bot.errors import UserFacingError
from bot.features.widgets.guards import require_client_member, require_hub_guild


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
    from bot.features.recipes.hub.onboarding.service import _ProvisionOutcome

    bot = recipe_context.bot
    core = recipe_context.core
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
    client_id: int,
    guild: discord.Guild | None = None,
    member: discord.abc.User | None = None,
) -> OpenModal:
    require_hub_guild(recipe_context.bot, guild)
    client = await _require_client(recipe_context, client_id)
    if guild is not None and member is not None:
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
    client_id: int,
    guild: discord.Guild | None = None,
    member: discord.abc.User | None = None,
) -> OpenEphemeralView:
    require_hub_guild(recipe_context.bot, guild)
    client = await _require_client(recipe_context, client_id)
    if guild is not None and member is not None:
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
    guild: discord.Guild,
    bot_member: discord.Member,
    client_id: int,
    member: discord.abc.User | None = None,
) -> Any:
    from bot.features.recipes.hub.clients.deletion import delete_client_resources

    require_hub_guild(recipe_context.bot, guild)
    client = await _require_client(recipe_context, client_id)
    if member is not None:
        require_client_member(
            guild, member, client, popup="client_role_required_delete", allow_non_member=True
        )
    return await delete_client_resources(
        guild,
        bot_member,
        client=client,
        client_repo=recipe_context.core.store.clients,
        network_repo=recipe_context.core.store.networks,
        context=recipe_context.core,
    )


@recipe("client.edit_profile")
async def edit_client_profile(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    client_id: int,
    display_name: str,
    profile_image: discord.Attachment | None = None,
    view_registry: Any,
    member: discord.abc.User | None = None,
) -> Any:
    from bot.features.recipes.hub.clients.profile_edit import apply_client_profile_edit

    require_hub_guild(recipe_context.bot, guild)
    client = await _require_client(recipe_context, client_id)
    if member is not None:
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
        view_registry=view_registry,
    )


@recipe("client.toggle_timecode")
async def toggle_client_timecode(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    client_id: int,
    view_registry: Any,
    member: discord.abc.User | None = None,
) -> Any:
    from bot.features.recipes.hub.clients.profile_sync import refresh_client_profile_message

    require_hub_guild(recipe_context.bot, guild)
    client = await _require_client(recipe_context, client_id)
    if member is not None:
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
        view_registry=view_registry,
    )
    return updated


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
