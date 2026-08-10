from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.domain.errors import ProfileValidationError
from bot.domain.profile_image import ProfileImage, ProfileImageAttachment
from bot.domain.server_request import ServerRequest, ServerRequestStatus
from bot.media.image import (
    download_profile_image_from_url,
    normalize_image_bytes,
    read_profile_image_attachment,
)
from bot.ui.view_registry import ViewRegistry

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
    requester: discord.abc.User,
    server_name: str,
    request_id: int,
) -> discord.Embed:
    from bot.messages import render_embed

    return render_embed(
        "join_request_moderator",
        requester_mention=requester.mention,
        request_id=request_id,
        client_name=server_name,
    )


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


@dataclass
class _ProvisionOutcome:
    success: bool
    client_role: discord.Role | None = None
    profile_channel: discord.TextChannel | None = None
    error: str | None = None


class ServerRequestService:
    def __init__(
        self,
        context: BotContext,
        bot: NetworkRelayBot,
        *,
        view_registry: ViewRegistry,
    ) -> None:
        self._context = context
        self._bot = bot
        self._view_registry = view_registry

    async def submit_request(
        self,
        guild: discord.Guild,
        *,
        requester: discord.abc.User,
        server_name: str,
        profile_image: ProfileImageAttachment,
        display_name: str | None = None,
    ) -> SubmitRequestResult:
        name = server_name.strip()
        if not name:
            return SubmitRequestResult(success=False, error="Name cannot be empty.")
        label = (display_name or name).strip()
        if not label:
            return SubmitRequestResult(success=False, error="Name cannot be empty.")

        existing_pending = await self._context.server_request_repo.get_pending_for_requester(
            requester.id,
        )
        if existing_pending is not None:
            return SubmitRequestResult(
                success=False,
                error="You already have a pending join request.",
            )

        existing_client = await self._context.client_repo.get_by_server_name(
            guild.id,
            name,
        )
        if existing_client is not None:
            return SubmitRequestResult(
                success=False,
                error=f"A client named {name!r} already exists on this hub.",
            )

        try:
            image = await read_profile_image_attachment(profile_image)
        except ProfileValidationError as exc:
            return SubmitRequestResult(success=False, error=str(exc))

        request = await self._context.server_request_repo.create(
            guild_id=guild.id,
            network_id=None,
            requester_user_id=requester.id,
            server_name=name,
            display_name=label,
            profile_image_url=profile_image.url,
            profile_image_data=image.data,
        )

        from bot.hub.resolve import resolve_join_requests_channel

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

        view = self._view_registry.register_moderator_review_view(request.id)
        embed = build_moderator_request_embed(
            requester=requester,
            server_name=request.server_name,
            request_id=request.id,
        )
        try:
            from bot.hub.resolve import resolve_human_moderator_role
            from bot.relay.delivery import build_moderator_join_request_send_kwargs

            send_kwargs = build_moderator_join_request_send_kwargs(
                resolve_human_moderator_role(guild),
            )
            message = await requests_channel.send(
                embed=embed,
                file=discord.File(fp=io.BytesIO(image.data), filename="profile.png"),
                view=view,
                **send_kwargs,
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

        try:
            image = await _load_request_profile_image(request)
        except ProfileValidationError as exc:
            return ReviewRequestResult(success=False, error=str(exc))

        bot_member = guild.me
        if bot_member is None:
            return ReviewRequestResult(success=False, error="Bot member is unavailable.")

        try:
            result = await self._provision_client_from_request(
                guild,
                bot_member,
                request,
                image,
            )
        except Exception:
            logger.exception(
                "Join request approval provisioning failed",
                extra={"request_id": request_id},
            )
            return ReviewRequestResult(
                success=False,
                error="Client provisioning failed unexpectedly. Check bot logs.",
            )

        if not result.success:
            return ReviewRequestResult(success=False, error=result.error)

        requester = guild.get_member(request.requester_user_id)
        if requester is not None and result.client_role is not None:
            try:
                await requester.add_roles(
                    result.client_role,
                    reason=f"Approved client join request #{request.id}",
                )
            except discord.HTTPException as exc:
                logger.warning(
                    "Could not grant client role after approval",
                    extra={"request_id": request.id, "error": str(exc)},
                )

        await self._context.server_request_repo.resolve(
            request_id,
            status=ServerRequestStatus.APPROVED,
            resolved_by_user_id=moderator.id,
        )
        await self._context.client_cache.load_cache()
        if result.client_role is not None:
            from bot.hub.leaders import grant_leaders_channel_access

            leaders_sync = await grant_leaders_channel_access(
                guild,
                bot_member,
                self._context,
                result.client_role,
                access_role_name=self._bot.settings.network_access_role_name,
                operator_role_name=self._bot.settings.network_operator_role_name,
            )
        else:
            leaders_sync = None
        await self._finalize_review_message(guild, request, moderator, ServerRequestStatus.APPROVED)

        summary = "Client category created."
        if result.profile_channel is not None:
            summary = f"Created {result.profile_channel.mention}."
        if leaders_sync is not None and leaders_sync.failures:
            summary += (
                " Leaders access sync reported issues: "
                + "; ".join(leaders_sync.failures[:3])
                + ("…" if len(leaders_sync.failures) > 3 else "")
            )
        if requester is not None:
            await self._notify_requester(
                requester,
                approved=True,
                profile_channel=result.profile_channel,
            )
        return ReviewRequestResult(success=True, message=summary)

    async def _provision_client_from_request(
        self,
        guild: discord.Guild,
        bot_member: discord.Member,
        request: ServerRequest,
        image: ProfileImage,
    ) -> _ProvisionOutcome:
        from bot.clients.profile_post import build_client_profile_embed
        from bot.clients.profile_sync import refresh_client_profile_message
        from bot.clients.provision import ClientProvisionService
        from bot.media.emoji import EmojiService, emoji_sync_target_from_client

        provision_service = ClientProvisionService()
        try:
            provision = await provision_service.provision_client(
                guild,
                bot_member,
                server_name=request.server_name,
                access_role_name=self._bot.settings.network_access_role_name,
                operator_role_name=self._bot.settings.network_operator_role_name,
            )
        except ProfileValidationError as exc:
            return _ProvisionOutcome(success=False, error=str(exc))
        except discord.HTTPException as exc:
            return _ProvisionOutcome(success=False, error=f"Discord API error: {exc}")

        networks = await self._context.network_repo.list_all()
        network_keys = [n.key for n in networks]
        view = self._view_registry.register_client_profile_view(0, network_keys)
        embed = build_client_profile_embed(
            server_name=request.server_name,
            display_name=request.display_name,
            enabled=True,
        )
        starter = await provision.profile_channel.send(
            embed=embed,
            view=view,
            silent=True,
        )

        client = await self._context.client_repo.create(
            guild_id=guild.id,
            server_name=request.server_name,
            display_name=request.display_name,
            category_id=provision.category.id,
            client_role_id=provision.client_role.id,
            profile_channel_id=provision.profile_channel.id,
            profile_message_id=starter.id,
        )

        view = self._view_registry.register_client_profile_for_client(client, network_keys)
        await starter.edit(view=view)

        emoji_service = EmojiService()
        emoji_result = await emoji_service.sync_for_profile(
            guild,
            emoji_sync_target_from_client(
                client,
                source_channel_id=provision.profile_channel.id,
            ),
            image,
            previous_hash=None,
            previous_emoji_id=None,
            force=True,
        )
        if emoji_result.emoji_id is not None:
            await self._context.client_repo.update_emoji_fields(
                client.id,
                emoji_id=emoji_result.emoji_id,
                emoji_name=emoji_result.emoji_name,
                image_hash=emoji_result.image_hash,
                degraded_reason=emoji_result.degraded_reason,
            )
            client = await self._context.client_repo.get_by_id(client.id) or client

        await refresh_client_profile_message(
            self._bot,
            self._context,
            guild,
            client,
            view_registry=self._view_registry,
        )
        return _ProvisionOutcome(
            success=True,
            client_role=provision.client_role,
            profile_channel=provision.profile_channel,
        )

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
                await self._notify_requester(requester, approved=False)

        return ReviewRequestResult(success=True, message="The join request was denied.")

    async def _finalize_review_message(
        self,
        guild: discord.Guild,
        request: ServerRequest,
        moderator: discord.Member,
        status: ServerRequestStatus,
    ) -> None:
        if request.moderator_message_id is None:
            return
        from bot.hub.resolve import resolve_join_requests_channel

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
        profile_channel: discord.TextChannel | None = None,
    ) -> None:
        bot_user = self._bot.user
        if bot_user is not None and requester.id == bot_user.id:
            logger.debug(
                "Skipping join-request DM to bot user",
                extra={"user_id": requester.id, "approved": approved},
            )
            return
        if getattr(requester, "bot", False):
            logger.debug(
                "Skipping join-request DM to bot account",
                extra={"user_id": requester.id, "approved": approved},
            )
            return

        if approved:
            description = (
                "Your request to join **The Network** hub was approved.\n\n"
                "Open your **network-profile** channel and subscribe to networks "
                "with the buttons there. Connect your announcement channel to each "
                "**publish** channel via Channel Follow.\n"
            )
            if profile_channel is not None:
                description += f"\nProfile: {profile_channel.mention}"
            colour = discord.Colour.green()
            title = "Join request approved"
        else:
            description = "Your request to join **The Network** hub was denied."
            colour = discord.Colour.red()
            title = "Join request denied"

        embed = discord.Embed(title=title, description=description, colour=colour)
        try:
            await requester.send(embed=embed)
        except (discord.HTTPException, AttributeError):
            logger.debug(
                "Could not DM requester about review outcome",
                extra={"user_id": requester.id, "approved": approved},
            )
