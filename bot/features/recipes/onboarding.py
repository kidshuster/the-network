"""Onboarding / join-request domain recipes."""

from __future__ import annotations

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.contracts.widgets import OpenModal, recipe_handler
from bot.core.models.profile_image import ProfileImageAttachment
from bot.core.views import ViewRegistry
from bot.errors import UserFacingError
from bot.features.recipes.hub.onboarding.service import (
    ReviewRequestResult,
    ServerRequestService,
    SubmitRequestResult,
)
from bot.features.widgets.guards import require_hub_guild, require_manage_guild


@recipe("request.submit")
async def submit_request(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    requester: discord.abc.User,
    server_name: str,
    profile_image: ProfileImageAttachment,
    view_registry: ViewRegistry,
    display_name: str | None = None,
) -> SubmitRequestResult:
    require_hub_guild(recipe_context.bot, guild)
    if profile_image is None:
        raise UserFacingError(
            "A profile image is required.",
            title="Request Failed",
            code="profile_image_required",
        )
    return await ServerRequestService(
        recipe_context.core,
        recipe_context.bot,
        view_registry=view_registry,
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
    guild: discord.Guild | None,
    request_id: int,
    moderator: discord.Member,
    view_registry: ViewRegistry,
) -> ReviewRequestResult:
    require_hub_guild(recipe_context.bot, guild)
    require_manage_guild(moderator)
    return await ServerRequestService(
        recipe_context.core,
        recipe_context.bot,
        view_registry=view_registry,
    ).approve_request(
        guild,
        request_id=request_id,
        moderator=moderator,
    )


@recipe("request.deny")
async def deny_request(
    recipe_context: RecipeContext,
    *,
    request_id: int,
    moderator: discord.Member,
    view_registry: ViewRegistry,
    guild: discord.Guild | None = None,
) -> ReviewRequestResult:
    if guild is not None:
        require_hub_guild(recipe_context.bot, guild)
    require_manage_guild(moderator)
    return await ServerRequestService(
        recipe_context.core,
        recipe_context.bot,
        view_registry=view_registry,
    ).deny_request(
        request_id=request_id,
        moderator=moderator,
    )


@recipe("request.join.open")
async def open_join_request(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
) -> OpenModal:
    del recipe_context, interaction
    return OpenModal(
        template_id="join_network",
        submit=recipe_handler("request.submit"),
    )
