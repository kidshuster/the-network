"""Onboarding / join-request domain recipes."""

from __future__ import annotations

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.contracts.widgets import OpenModal, recipe_handler
from bot.core.models.profile_image import ProfileImageAttachment
from bot.errors import UserFacingError
from bot.features.recipes.hub.onboarding.service import (
    ReviewRequestResult,
    ServerRequestService,
    SubmitRequestResult,
)
from bot.features.widgets.guards import (
    interaction_actor,
    interaction_guild,
    interaction_view_registry,
    require_manage_guild,
)


@recipe("request.submit")
async def submit_request(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    server_name: str,
    profile_image: ProfileImageAttachment | discord.Attachment | None = None,
    display_name: str | None = None,
) -> SubmitRequestResult:
    guild = interaction_guild(recipe_context.bot, interaction)
    requester = interaction_actor(interaction)
    if profile_image is None:
        raise UserFacingError(
            "A profile image is required.",
            title="Request Failed",
            code="profile_image_required",
        )
    return await ServerRequestService(
        recipe_context.core,
        recipe_context.bot,
        view_registry=interaction_view_registry(interaction),
    ).submit_request(
        guild,
        requester=requester,
        server_name=server_name,
        profile_image=profile_image,
        display_name=display_name,
    )


@recipe("request.approve")
async def approve_request(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    request_id: int,
) -> ReviewRequestResult:
    guild = interaction_guild(recipe_context.bot, interaction)
    moderator = interaction_actor(interaction)
    require_manage_guild(moderator)
    return await ServerRequestService(
        recipe_context.core,
        recipe_context.bot,
        view_registry=interaction_view_registry(interaction),
    ).approve_request(
        guild,
        request_id=request_id,
        moderator=moderator,  # type: ignore[arg-type]
    )


@recipe("request.deny")
async def deny_request(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    request_id: int,
) -> ReviewRequestResult:
    interaction_guild(recipe_context.bot, interaction)
    moderator = interaction_actor(interaction)
    require_manage_guild(moderator)
    return await ServerRequestService(
        recipe_context.core,
        recipe_context.bot,
        view_registry=interaction_view_registry(interaction),
    ).deny_request(
        request_id=request_id,
        moderator=moderator,  # type: ignore[arg-type]
    )


@recipe("request.join.open")
async def open_join_request(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
) -> OpenModal:
    del recipe_context
    interaction_actor(interaction)
    return OpenModal(
        template_id="join_network",
        submit=recipe_handler("request.submit"),
    )
