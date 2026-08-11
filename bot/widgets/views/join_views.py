from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import discord

from bot.adapters.discord.checks import ensure_manage_guild
from bot.adapters.discord.errors import respond_to_error, respond_with_error
from bot.adapters.discord.responses import defer_ephemeral
from bot.widgets import modal_spec, render_embed
from bot.widgets.modals_builder import (
    add_modal_fields,
    modal_file_attachments,
    modal_text_value,
)
from bot.widgets.views._auth import validate_hub_modal_context
from bot.widgets.views._view_helpers import bind_item_callback
from bot.widgets.views.custom_ids import (
    join_network_button,
    request_approve_button,
    request_deny_button,
)

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)


class JoinNetworkModal(discord.ui.Modal):
    def __init__(self, bot: NetworkRelayBot) -> None:
        spec = modal_spec("join_network")
        super().__init__(title=spec.title)
        self._bot = bot
        self._fields = add_modal_fields(self, spec)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        response = await defer_ephemeral(interaction)
        validated = validate_hub_modal_context(
            self._bot,
            interaction,
            guild_only_key="hub_guild_only",
        )
        if isinstance(validated, str):
            await response.send(validated)
            return

        context = validated.context

        attachments = modal_file_attachments(self._fields["profile_image"])
        if not attachments:
            await respond_with_error(
                self._bot,
                interaction,
                response,
                "A profile image upload is required.",
                operation="join.submit",
                title="Request Failed",
            )
            return

        from bot.widgets.recipes.onboarding.service import ServerRequestService
        from bot.widgets.views.persistent_views import PersistentViewRegistry

        service = ServerRequestService(
            context,
            self._bot,
            view_registry=PersistentViewRegistry(self._bot),
        )
        name = modal_text_value(self._fields["name"])
        result = await service.submit_request(
            validated.guild,
            requester=interaction.user,
            server_name=name,
            profile_image=attachments[0],
        )
        if not result.success:
            await respond_with_error(
                self._bot,
                interaction,
                response,
                result.error or "Unknown error",
                operation="join.submit",
                title="Request Failed",
            )
            return

        await response.send(
            embed=render_embed(
                "join_request_submitted",
                client_name=result.server_name or "—",
            ),
            ephemeral=True,
        )


class JoinNetworkView(discord.ui.View):
    def __init__(self, bot: NetworkRelayBot) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        button: discord.ui.Button[Any] = discord.ui.Button(
            label="Join Network",
            style=discord.ButtonStyle.success,
            custom_id=join_network_button(),
        )
        bind_item_callback(button, self._join_callback)
        self.add_item(button)

    async def _join_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(JoinNetworkModal(self._bot))


class ModeratorReviewView(discord.ui.View):
    def __init__(self, bot: NetworkRelayBot, request_id: int) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._request_id = request_id

        approve: discord.ui.Button[Any] = discord.ui.Button(
            label="Accept",
            style=discord.ButtonStyle.success,
            custom_id=request_approve_button(request_id),
        )
        bind_item_callback(approve, self._approve_callback)
        self.add_item(approve)

        deny: discord.ui.Button[Any] = discord.ui.Button(
            label="Deny",
            style=discord.ButtonStyle.danger,
            custom_id=request_deny_button(request_id),
        )
        bind_item_callback(deny, self._deny_callback)
        self.add_item(deny)

    async def _approve_callback(self, interaction: discord.Interaction) -> None:
        await self._handle_review(interaction, approved=True)

    async def _deny_callback(self, interaction: discord.Interaction) -> None:
        await self._handle_review(interaction, approved=False)

    async def _handle_review(self, interaction: discord.Interaction, *, approved: bool) -> None:
        if not await ensure_manage_guild(interaction):
            return

        response = await defer_ephemeral(interaction)
        context = self._bot.bot_context
        if context is None:
            await response.send_text("bot_not_ready")
            return

        member = cast(discord.Member, interaction.user)

        from bot.widgets.recipes.onboarding.service import ServerRequestService
        from bot.widgets.views.persistent_views import PersistentViewRegistry

        service = ServerRequestService(
            context,
            self._bot,
            view_registry=PersistentViewRegistry(self._bot),
        )
        try:
            if approved:
                result = await service.approve_request(
                    interaction.guild,
                    request_id=self._request_id,
                    moderator=member,
                )
            else:
                result = await service.deny_request(
                    request_id=self._request_id,
                    moderator=member,
                )
        except Exception as error:
            await respond_to_error(
                self._bot,
                interaction,
                response,
                error,
                operation="join.review",
            )
            return

        if not result.success:
            await respond_with_error(
                self._bot,
                interaction,
                response,
                result.error or "Unknown error",
                operation="join.review",
                title="Review Failed",
            )
            return

        label = "approved" if approved else "denied"
        await response.send(
            embed=render_embed(
                "review_success",
                label=label.title(),
                colour="green" if approved else "orange",
                description=result.message or f"The request was {label}.",
            ),
            ephemeral=True,
        )
