from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.domain.errors import ProfileValidationError
from bot.domain.profile_image import ProfileImage
from bot.domain.server_request import ServerRequest, ServerRequestStatus
from bot.services.image_service import (
    download_profile_image_from_url,
    normalize_image_bytes,
    read_profile_image_attachment,
)
from bot.ui.profile_views import EditProfileView

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubmitRequestResult:
    success: bool
    error: str | None = None
    server_name: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class ReviewRequestResult:
    success: bool
    error: str | None = None
    message: str | None = None


def build_moderator_request_embed(
    *,
    network_display_name: str,
    requester: discord.abc.User,
    server_name: str,
    display_name: str,
    request_id: int,
) -> discord.Embed:
    embed = discord.Embed(
        title="Server join request",
        description=f"Network **{network_display_name}**",
        colour=discord.Colour.gold(),
    )
    embed.add_field(name="Requester", value=requester.mention, inline=True)
    embed.add_field(name="Request ID", value=f"`{request_id}`", inline=True)
    embed.add_field(name="Server name", value=server_name, inline=False)
    embed.add_field(name="Display name", value=display_name, inline=False)
    embed.set_footer(text="The Network • moderator review")
    return embed


async def _load_request_profile_image(request: ServerRequest) -> ProfileImage:
    if request.profile_image_data:
        return normalize_image_bytes(request.profile_image_data)
    if request.profile_image_url.strip():
        return await download_profile_image_from_url(request.profile_image_url)
    raise ProfileValidationError("Join request is missing a stored profile image.")


def build_resolved_request_embed(
    embed: discord.Embed,
    *,
    status: ServerRequestStatus,
    moderator: discord.abc.User,
) -> discord.Embed:
    resolved = embed.copy()
    if status == ServerRequestStatus.APPROVED:
        colour = discord.Colour.green()
    else:
        colour = discord.Colour.red()
    resolved.colour = colour
    resolved.title = f"{embed.title} — {status.value.title()}"
    resolved.add_field(name="Reviewed by", value=moderator.mention, inline=False)
    return resolved


class ServerRequestService:
    def __init__(self, context: BotContext, bot: NetworkRelayBot) -> None:
        self._context = context
        self._bot = bot

    async def submit_request(
        self,
        guild: discord.Guild,
        *,
        requester: discord.abc.User,
        network_key: str,
        server_name: str,
        display_name: str,
        profile_image: discord.Attachment,
    ) -> SubmitRequestResult:
        if not server_name.strip():
            return SubmitRequestResult(success=False, error="Server name cannot be empty.")
        if not display_name.strip():
            return SubmitRequestResult(success=False, error="Display name cannot be empty.")

        network = await self._context.network_repo.get_by_key(network_key)
        if network is None:
            return SubmitRequestResult(
                success=False,
                error=f"Network `{network_key.strip().lower()}` was not found.",
            )

        existing_pending = await self._context.server_request_repo.get_pending_for_requester(
            network.id,
            requester.id,
        )
        if existing_pending is not None:
            return SubmitRequestResult(
                success=False,
                error="You already have a pending join request for this network.",
            )

        existing_server = await self._context.profile_repo.get_by_network_and_server_name(
            network.id,
            server_name,
        )
        if existing_server is not None:
            return SubmitRequestResult(
                success=False,
                error=f"A server named {server_name!r} already exists on this network.",
            )

        try:
            image = await read_profile_image_attachment(profile_image)
        except ProfileValidationError as exc:
            return SubmitRequestResult(success=False, error=str(exc))

        request = await self._context.server_request_repo.create(
            guild_id=guild.id,
            network_id=network.id,
            requester_user_id=requester.id,
            server_name=server_name,
            display_name=display_name,
            profile_image_url=profile_image.url,
            profile_image_data=image.data,
        )

        from bot.services.guild_channels import resolve_join_requests_channel
        from bot.ui.join_views import ModeratorReviewView

        requests_channel = resolve_join_requests_channel(guild)
        if requests_channel is None:
            return SubmitRequestResult(
                success=False,
                error="Moderator `#join-requests` channel was not found in this guild.",
            )

        bot_member = guild.me
        if bot_member is None:
            return SubmitRequestResult(success=False, error="Bot member is unavailable.")

        perms = requests_channel.permissions_for(bot_member)
        if not perms.view_channel or not perms.send_messages or not perms.embed_links:
            return SubmitRequestResult(
                success=False,
                error=f"The bot cannot post review requests in {requests_channel.mention}.",
            )

        view = ModeratorReviewView(self._bot, request.id)
        self._bot.add_view(view)
        embed = build_moderator_request_embed(
            network_display_name=network.display_name,
            requester=requester,
            server_name=request.server_name,
            display_name=request.display_name,
            request_id=request.id,
        )
        try:
            message = await requests_channel.send(
                embed=embed,
                file=discord.File(fp=io.BytesIO(image.data), filename="profile.png"),
                view=view,
            )
        except discord.HTTPException as exc:
            return SubmitRequestResult(success=False, error=f"Discord API error: {exc}")

        await self._context.server_request_repo.set_moderator_message_id(request.id, message.id)
        return SubmitRequestResult(
            success=True,
            server_name=request.server_name,
            display_name=request.display_name,
        )

    async def approve_request(
        self,
        guild: discord.Guild | None,
        *,
        request_id: int,
        moderator: discord.Member,
    ) -> ReviewRequestResult:
        if guild is None or guild.id != self._bot.settings.guild_id:
            return ReviewRequestResult(success=False, error="Invalid guild for approval.")

        request = await self._context.server_request_repo.get_by_id(request_id)
        if request is None:
            return ReviewRequestResult(success=False, error="Join request was not found.")
        if request.status != ServerRequestStatus.PENDING:
            return ReviewRequestResult(success=False, error="This request was already reviewed.")

        network = await self._context.network_repo.get_by_id(request.network_id)
        if network is None:
            return ReviewRequestResult(
                success=False,
                error="Network for this request was not found.",
            )

        try:
            image = await _load_request_profile_image(request)
        except ProfileValidationError as exc:
            return ReviewRequestResult(success=False, error=str(exc))

        bot_member = guild.me
        if bot_member is None:
            return ReviewRequestResult(success=False, error="Bot member is unavailable.")

        result = await self._context.profile_sync.create_profile(
            guild,
            bot_member,
            server_name=request.server_name,
            display_name=request.display_name,
            network_key=network.key,
            profile_image_bytes=image.data,
        )

        if not result.success or result.profile_channel is None or result.server_role is None:
            return ReviewRequestResult(
                success=False,
                error=result.error or "Server provisioning failed.",
            )

        if result.starter_message is not None and result.profile_channel is not None:
            profile_view = EditProfileView(self._bot, result.profile_channel.id)
            self._bot.add_view(profile_view)
            try:
                await result.starter_message.edit(view=profile_view)
            except discord.HTTPException:
                logger.warning(
                    "Could not attach edit profile view after approval",
                    extra={"profile_channel_id": result.profile_channel.id},
                )

        requester = guild.get_member(request.requester_user_id)
        if requester is not None:
            try:
                await requester.add_roles(
                    result.server_role,
                    reason=f"Approved network join request #{request.id}",
                )
            except discord.HTTPException as exc:
                logger.warning(
                    "Could not grant partner role after approval",
                    extra={
                        "request_id": request.id,
                        "user_id": request.requester_user_id,
                        "error": str(exc),
                    },
                )

        await self._context.server_request_repo.resolve(
            request_id,
            status=ServerRequestStatus.APPROVED,
            resolved_by_user_id=moderator.id,
        )
        await self._finalize_review_message(guild, request, moderator, ServerRequestStatus.APPROVED)

        summary = f"Created {result.feed_channel.mention}."
        if requester is not None:
            await self._notify_requester(
                requester,
                approved=True,
                network_display_name=network.display_name,
                feed_channel=result.feed_channel,
                profile_channel=result.profile_channel,
            )
        return ReviewRequestResult(success=True, message=summary)

    async def deny_request(
        self,
        *,
        request_id: int,
        moderator: discord.Member,
    ) -> ReviewRequestResult:
        request = await self._context.server_request_repo.get_by_id(request_id)
        if request is None:
            return ReviewRequestResult(success=False, error="Join request was not found.")
        if request.status != ServerRequestStatus.PENDING:
            return ReviewRequestResult(success=False, error="This request was already reviewed.")

        await self._context.server_request_repo.resolve(
            request_id,
            status=ServerRequestStatus.DENIED,
            resolved_by_user_id=moderator.id,
        )

        guild = self._bot.get_guild(request.guild_id)
        if guild is not None:
            await self._finalize_review_message(
                guild, request, moderator, ServerRequestStatus.DENIED
            )
            requester = guild.get_member(request.requester_user_id)
            if requester is not None:
                network = await self._context.network_repo.get_by_id(request.network_id)
                display = network.display_name if network is not None else "the network"
                await self._notify_requester(
                    requester,
                    approved=False,
                    network_display_name=display,
                )

        return ReviewRequestResult(success=True, message="The join request was denied.")

    async def _finalize_review_message(
        self,
        guild: discord.Guild,
        request,
        moderator: discord.Member,
        status: ServerRequestStatus,
    ) -> None:
        if request.moderator_message_id is None:
            return
        from bot.services.guild_channels import resolve_join_requests_channel

        channel = resolve_join_requests_channel(guild)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(request.moderator_message_id)
        except discord.HTTPException:
            return
        if not message.embeds:
            return
        resolved_embed = build_resolved_request_embed(
            message.embeds[0],
            status=status,
            moderator=moderator,
        )
        try:
            await message.edit(embed=resolved_embed, view=None)
        except discord.HTTPException:
            logger.warning(
                "Could not update moderator review message",
                extra={"message_id": message.id, "request_id": request.id},
            )

    async def _notify_requester(
        self,
        requester: discord.Member,
        *,
        approved: bool,
        network_display_name: str,
        feed_channel: discord.TextChannel | None = None,
        profile_channel: discord.TextChannel | None = None,
    ) -> None:
        if approved:
            description = (
                f"Your request to join **{network_display_name}** was approved.\n\n"
                "Open your feed channel and use **Subscribe to Me!** (Channel Follow) "
                "to connect your announcement channel. Use the pinned **Edit Profile** "
                "button to update your display name or image.\n"
            )
            if feed_channel is not None:
                description += f"\nChannel: {feed_channel.mention}"
            colour = discord.Colour.green()
            title = "Join request approved"
        else:
            description = f"Your request to join **{network_display_name}** was denied."
            colour = discord.Colour.red()
            title = "Join request denied"

        embed = discord.Embed(title=title, description=description, colour=colour)
        try:
            await requester.send(embed=embed)
        except discord.HTTPException:
            logger.debug(
                "Could not DM requester about review outcome",
                extra={"user_id": requester.id, "approved": approved},
            )
