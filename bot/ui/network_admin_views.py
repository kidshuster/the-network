from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.cogs._checks import ensure_manage_guild
from bot.cogs._responses import defer_ephemeral
from bot.messages import modal_spec, render_embed, render_text
from bot.messages.modals_builder import add_modal_fields
from bot.services.network_admin import create_network, delete_network
from bot.services.network_admin_sticky import refresh_network_admin_sticky_from_settings
from bot.ui._auth import validate_hub_modal_context
from bot.ui.custom_ids import network_create_button, network_delete_button
from bot.ui.persistent_views import PersistentViewRegistry

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)


class CreateNetworkModal(discord.ui.Modal):
    def __init__(self, bot: NetworkRelayBot) -> None:
        spec = modal_spec("create_network")
        super().__init__(title=spec.title)
        self._bot = bot
        self._fields = add_modal_fields(self, spec)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await ensure_manage_guild(interaction):
            return

        response = await defer_ephemeral(interaction)
        validated = validate_hub_modal_context(self._bot, interaction)
        if isinstance(validated, str):
            await response.send(validated, ephemeral=True)
            return

        guild = validated.guild
        context = validated.context
        key = self._fields["key"].component.value.strip()
        display_name = self._fields["display_name"].component.value.strip()
        view_registry = PersistentViewRegistry(self._bot)
        result = await create_network(
            context,
            self._bot,
            guild,
            key=key,
            display_name=display_name,
            view_registry=view_registry,
        )
        if not result.success or result.network is None:
            await response.send(
                embed=render_embed(
                    "command_failure",
                    title="Network Create Failed",
                    description=result.error or "Unknown error",
                ),
                ephemeral=True,
            )
            return

        admin_channel = interaction.channel
        if isinstance(admin_channel, discord.TextChannel):
            await refresh_network_admin_sticky_from_settings(
                context,
                guild,
                view_registry.register_network_admin_view(),
            )

        await response.send(
            embed=render_embed(
                "network_created",
                key=result.network.key,
                display_name=result.network.display_name,
                updated_count=result.updated_profile_count if result.updated_profile_count else "",
                relinked="1" if result.relinked_subscription_count else "",
            ),
            ephemeral=True,
        )


class DeleteNetworkModal(discord.ui.Modal):
    def __init__(self, bot: NetworkRelayBot) -> None:
        spec = modal_spec("delete_network")
        super().__init__(title=spec.title)
        self._bot = bot
        self._fields = add_modal_fields(self, spec)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await ensure_manage_guild(interaction):
            return

        response = await defer_ephemeral(interaction)
        validated = validate_hub_modal_context(self._bot, interaction)
        if isinstance(validated, str):
            await response.send(validated, ephemeral=True)
            return

        guild = validated.guild
        context = validated.context
        key = self._fields["key"].component.value.strip()
        view_registry = PersistentViewRegistry(self._bot)
        result = await delete_network(
            context,
            self._bot,
            guild,
            key=key,
            view_registry=view_registry,
        )
        if not result.success:
            if result.error and "not found" in result.error.lower():
                await response.send(result.error, ephemeral=True)
            else:
                await response.send(
                    render_text("network_delete_failed"),
                    ephemeral=True,
                )
            return

        await refresh_network_admin_sticky_from_settings(
            context,
            guild,
            view_registry.register_network_admin_view(),
        )

        await response.send(
            render_text("network_deleted", key=result.network_key or key),
            ephemeral=True,
        )


class NetworkAdminView(discord.ui.View):
    def __init__(self, bot: NetworkRelayBot) -> None:
        super().__init__(timeout=None)
        self._bot = bot

        create = discord.ui.Button(
            label="Create Network",
            style=discord.ButtonStyle.success,
            custom_id=network_create_button(),
        )
        create.callback = self._create_callback
        self.add_item(create)

        delete = discord.ui.Button(
            label="Delete Network",
            style=discord.ButtonStyle.danger,
            custom_id=network_delete_button(),
        )
        delete.callback = self._delete_callback
        self.add_item(delete)

    async def _create_callback(self, interaction: discord.Interaction) -> None:
        if not await ensure_manage_guild(interaction):
            return
        await interaction.response.send_modal(CreateNetworkModal(self._bot))

    async def _delete_callback(self, interaction: discord.Interaction) -> None:
        if not await ensure_manage_guild(interaction):
            return
        await interaction.response.send_modal(DeleteNetworkModal(self._bot))
