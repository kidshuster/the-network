from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.messages import render_embed, render_text
from bot.messages import modal_spec
from bot.messages.modals_builder import add_modal_fields
from bot.services.network_admin import create_network, delete_network
from bot.services.network_admin_sticky import refresh_network_admin_sticky_from_settings
from bot.ui.custom_ids import network_create_button, network_delete_button

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)


def _require_manage_guild(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.guild_permissions.manage_guild:
        return False
    return True


class CreateNetworkModal(discord.ui.Modal):
    def __init__(self, bot: NetworkRelayBot) -> None:
        spec = modal_spec("create_network")
        super().__init__(title=spec.title)
        self._bot = bot
        self._fields = add_modal_fields(self, spec)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not _require_manage_guild(interaction):
            await interaction.response.send_message(
                render_text("manage_guild_required"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or guild.id != self._bot.settings.guild_id:
            await interaction.followup.send(render_text("central_guild_only"), ephemeral=True)
            return

        context = self._bot.bot_context
        if context is None:
            await interaction.followup.send(render_text("bot_not_ready"), ephemeral=True)
            return

        key = self._fields["key"].component.value.strip()
        display_name = self._fields["display_name"].component.value.strip()
        result = await create_network(
            context,
            self._bot,
            guild,
            key=key,
            display_name=display_name,
        )
        if not result.success or result.network is None:
            await interaction.followup.send(
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
            await refresh_network_admin_sticky_from_settings(self._bot, context, guild)

        await interaction.followup.send(
            embed=render_embed(
                "network_created",
                key=result.network.key,
                display_name=result.network.display_name,
                updated_count=result.updated_profile_count if result.updated_profile_count else "",
                reenabled="1" if result.reenabled else "",
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
        if not _require_manage_guild(interaction):
            await interaction.response.send_message(
                render_text("manage_guild_required"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or guild.id != self._bot.settings.guild_id:
            await interaction.followup.send(render_text("central_guild_only"), ephemeral=True)
            return

        context = self._bot.bot_context
        if context is None:
            await interaction.followup.send(render_text("bot_not_ready"), ephemeral=True)
            return

        key = self._fields["key"].component.value.strip()
        result = await delete_network(context, self._bot, guild, key=key)
        if not result.success:
            if result.error and "not found" in result.error.lower():
                await interaction.followup.send(result.error, ephemeral=True)
            else:
                await interaction.followup.send(
                    render_text("network_delete_failed"),
                    ephemeral=True,
                )
            return

        await refresh_network_admin_sticky_from_settings(self._bot, context, guild)

        await interaction.followup.send(
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
            label="Disable Network",
            style=discord.ButtonStyle.danger,
            custom_id=network_delete_button(),
        )
        delete.callback = self._delete_callback
        self.add_item(delete)

    async def _create_callback(self, interaction: discord.Interaction) -> None:
        if not _require_manage_guild(interaction):
            await interaction.response.send_message(
                render_text("manage_guild_required"),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(CreateNetworkModal(self._bot))

    async def _delete_callback(self, interaction: discord.Interaction) -> None:
        if not _require_manage_guild(interaction):
            await interaction.response.send_message(
                render_text("manage_guild_required"),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(DeleteNetworkModal(self._bot))
