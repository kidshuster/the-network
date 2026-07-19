from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.ui.custom_ids import (
    join_server_button,
    request_approve_button,
    request_deny_button,
)

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)


class JoinRequestModal(discord.ui.Modal, title="Join the network"):
    def __init__(self, bot: NetworkRelayBot, network_key: str) -> None:
        super().__init__()
        self._bot = bot
        self._network_key = network_key

        self.server_name = discord.ui.Label(
            text="Server name",
            description="Your Discord server name (cannot be changed later)",
            component=discord.ui.TextInput(
                placeholder="My Community Server",
                max_length=100,
                required=True,
            ),
        )
        self.display_name = discord.ui.Label(
            text="Display name",
            description="Label shown on relayed messages",
            component=discord.ui.TextInput(
                placeholder="My Server",
                max_length=100,
                required=True,
            ),
        )
        self.profile_image = discord.ui.Label(
            text="Profile image",
            description="Upload a PNG, JPG, WebP, or GIF",
            component=discord.ui.FileUpload(required=True, max_values=1),
        )
        self.add_item(self.server_name)
        self.add_item(self.display_name)
        self.add_item(self.profile_image)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        if guild is None or guild.id != self._bot.settings.guild_id:
            await interaction.followup.send("This request can only be submitted in the hub guild.")
            return

        context = self._bot.bot_context
        if context is None:
            await interaction.followup.send("Bot is not ready yet.")
            return

        attachments = self.profile_image.component.values
        if not attachments:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Request Failed",
                    description="A profile image upload is required.",
                    colour=discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return

        from bot.services.server_request_service import ServerRequestService

        service = ServerRequestService(context, self._bot)
        result = await service.submit_request(
            guild,
            requester=user,
            network_key=self._network_key,
            server_name=self.server_name.component.value.strip(),
            display_name=self.display_name.component.value.strip(),
            profile_image=attachments[0],
        )
        if not result.success:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Request Failed",
                    description=result.error or "Unknown error",
                    colour=discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Request Submitted",
            description=(
                "Your join request was sent to moderators for review. "
                "You will be notified when it is approved or denied."
            ),
            colour=discord.Colour.green(),
        )
        embed.add_field(name="Server name", value=result.server_name or "—", inline=True)
        embed.add_field(name="Display name", value=result.display_name or "—", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)


class JoinServerView(discord.ui.View):
    def __init__(self, bot: NetworkRelayBot, network_key: str) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._network_key = network_key
        button = discord.ui.Button(
            label="Join Server",
            style=discord.ButtonStyle.success,
            custom_id=join_server_button(network_key),
        )
        button.callback = self._join_callback
        self.add_item(button)

    async def _join_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            JoinRequestModal(self._bot, self._network_key),
        )


class ModeratorReviewView(discord.ui.View):
    def __init__(self, bot: NetworkRelayBot, request_id: int) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._request_id = request_id

        approve = discord.ui.Button(
            label="Accept",
            style=discord.ButtonStyle.success,
            custom_id=request_approve_button(request_id),
        )
        approve.callback = self._approve_callback
        self.add_item(approve)

        deny = discord.ui.Button(
            label="Deny",
            style=discord.ButtonStyle.danger,
            custom_id=request_deny_button(request_id),
        )
        deny.callback = self._deny_callback
        self.add_item(deny)

    async def _approve_callback(self, interaction: discord.Interaction) -> None:
        await self._handle_review(interaction, approved=True)

    async def _deny_callback(self, interaction: discord.Interaction) -> None:
        await self._handle_review(interaction, approved=False)

    async def _handle_review(self, interaction: discord.Interaction, *, approved: bool) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need **Manage Server** to review join requests.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        context = self._bot.bot_context
        if context is None:
            await interaction.followup.send("Bot is not ready yet.")
            return

        from bot.services.server_request_service import ServerRequestService

        service = ServerRequestService(context, self._bot)
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

        if not result.success:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Review Failed",
                    description=result.error or "Unknown error",
                    colour=discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return

        label = "approved" if approved else "denied"
        await interaction.followup.send(
            embed=discord.Embed(
                title=f"Request {label.title()}",
                description=result.message or f"The request was {label}.",
                colour=discord.Colour.green() if approved else discord.Colour.orange(),
            ),
            ephemeral=True,
        )
