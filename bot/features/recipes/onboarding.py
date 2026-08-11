"""Onboarding / join-request domain recipes."""

from __future__ import annotations

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.core.models.profile_image import ProfileImageAttachment
from bot.core.views import ViewRegistry
from bot.features.recipes.hub.onboarding.service import (
    ReviewRequestResult,
    ServerRequestService,
    SubmitRequestResult,
)


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
) -> ReviewRequestResult:
    return await ServerRequestService(
        recipe_context.core,
        recipe_context.bot,
        view_registry=view_registry,
    ).deny_request(
        request_id=request_id,
        moderator=moderator,
    )
