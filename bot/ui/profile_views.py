from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from bot.cogs._responses import defer_ephemeral
from bot.messages import modal_spec, render_embed, render_text
from bot.messages.modals_builder import add_modal_fields, modal_file_attachments, modal_text_value
from bot.ui._auth import MembershipPolicy, ensure_client_access, validate_client_modal_context
from bot.ui._view_helpers import bind_item_callback
from bot.ui.custom_ids import profile_edit_button

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)


class EditClientProfileModal(discord.ui.Modal):
    def __init__(
        self,
        bot: NetworkRelayBot,
        client_id: int,
        current_display_name: str,
    ) -> None:
        spec = modal_spec("edit_client_profile")
        super().__init__(title=spec.title)
        self._bot = bot
        self._client_id = client_id
        self._fields = add_modal_fields(self, spec)
        display_input = self._fields["display_name"].component
        assert isinstance(display_input, discord.ui.TextInput)
        display_input.default = current_display_name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        response = await defer_ephemeral(interaction)
        validated = validate_client_modal_context(self._bot, interaction)
        if isinstance(validated, str):
            await response.send(validated)
            return

        context = validated.context

        client = await context.store.clients.get_by_id(self._client_id)
        if client is None:
            await response.send_text("client_not_found")
            return

        if not await ensure_client_access(
            interaction,
            validated.guild,
            client,
            popup_key="client_role_required_edit",
            membership_policy=MembershipPolicy.ALLOW_NON_MEMBER,
            via="followup",
            ephemeral=None,
        ):
            return

        display_name = modal_text_value(self._fields["display_name"])
        profile_image: discord.Attachment | None = None
        attachments = modal_file_attachments(self._fields["profile_image"])
        if attachments:
            profile_image = attachments[0]

        from bot.clients.profile_edit import apply_client_profile_edit
        from bot.ui.persistent_views import PersistentViewRegistry

        result = await apply_client_profile_edit(
            self._bot,
            context,
            validated.guild,
            client_id=self._client_id,
            display_name=display_name,
            profile_image=profile_image,
            view_registry=PersistentViewRegistry(self._bot),
        )
        if not result.success or result.client is None:
            await response.send(
                embed=render_embed(
                    "profile_update_failed",
                    description=result.error or "Unknown error",
                ),
                ephemeral=True,
            )
            return

        warnings = ""
        if result.warnings:
            warnings = "\n".join(f"• {warning}" for warning in result.warnings)

        await response.send(
            embed=render_embed(
                "profile_updated",
                display_name=result.client.display_name,
                warnings=warnings,
            ),
            ephemeral=True,
        )


class EditProfileView(discord.ui.View):
    """Legacy alias — use NetworkProfileView for new clients."""

    def __init__(self, bot: NetworkRelayBot, client_id: int) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._client_id = client_id
        button: discord.ui.Button[Any] = discord.ui.Button(
            label="Edit Profile",
            style=discord.ButtonStyle.primary,
            custom_id=profile_edit_button(client_id),
        )
        bind_item_callback(button, self._edit_callback)
        self.add_item(button)

    async def _edit_callback(self, interaction: discord.Interaction) -> None:
        context = self._bot.bot_context
        if context is None:
            await interaction.response.send_message(render_text("bot_not_ready"), ephemeral=True)
            return
        client = await context.store.clients.get_by_id(self._client_id)
        if client is None:
            await interaction.response.send_message(
                render_text("client_not_found"),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            EditClientProfileModal(self._bot, self._client_id, client.display_name),
        )


class DeleteClientConfirmView(discord.ui.View):
    def __init__(self, bot: NetworkRelayBot, client_id: int) -> None:
        super().__init__(timeout=60)
        self._bot = bot
        self._client_id = client_id

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]

    @discord.ui.button(
        label="Delete permanently",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[Any],
    ) -> None:
        response = await defer_ephemeral(interaction)
        guild = interaction.guild
        if guild is None:
            await response.send_text("invalid_guild")
            return

        context = self._bot.bot_context
        if context is None:
            await response.send_text("bot_not_ready")
            return

        client = await context.store.clients.get_by_id(self._client_id)
        if client is None:
            await response.send_text("client_not_found")
            return

        if not await ensure_client_access(
            interaction,
            guild,
            client,
            popup_key="client_role_required_delete",
            membership_policy=MembershipPolicy.REQUIRED,
            via="followup",
            ephemeral=None,
        ):
            return

        bot_member = guild.me
        if bot_member is None:
            await response.send_text("bot_member_unavailable_brief")
            return

        from bot.clients.deletion import ClientDeletionService

        result = await ClientDeletionService().delete_client(
            guild,
            bot_member,
            client=client,
            client_repo=context.store.clients,
            network_repo=context.store.networks,
            context=context,
        )
        if not result.success:
            await response.send(
                embed=render_embed(
                    "delete_client_failed",
                    error=result.error or "Unknown error",
                ),
            )
            return

        await response.send(
            embed=render_embed(
                "delete_client_success",
                server_name=client.server_name,
            ),
        )

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[Any],
    ) -> None:
        await interaction.response.edit_message(
            content=render_text("delete_client_cancelled"),
            view=None,
        )
