from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.ui.custom_ids import profile_edit_button

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)


class EditProfileView(discord.ui.View):
    def __init__(self, bot: NetworkRelayBot, profile_channel_id: int) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._profile_channel_id = profile_channel_id
        button = discord.ui.Button(
            label="Edit Profile",
            style=discord.ButtonStyle.primary,
            custom_id=profile_edit_button(profile_channel_id),
        )
        button.callback = self._edit_callback
        self.add_item(button)

    async def _edit_callback(self, interaction: discord.Interaction) -> None:
        context = self._bot.bot_context
        if context is None:
            await interaction.response.send_message("Bot is not ready yet.", ephemeral=True)
            return

        profile = await context.profile_repo.get_by_thread_id(self._profile_channel_id)
        if profile is None:
            await interaction.response.send_message(
                "This profile is no longer registered.",
                ephemeral=True,
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Could not resolve your membership.",
                ephemeral=True,
            )
            return

        if not member.guild_permissions.manage_guild:
            if profile.partner_role_id is None:
                await interaction.response.send_message(
                    "This profile has no partner role configured.",
                    ephemeral=True,
                )
                return
            server_role = (
                interaction.guild.get_role(profile.partner_role_id) if interaction.guild else None
            )
            if server_role is None or server_role not in member.roles:
                await interaction.response.send_message(
                    "You need the partner role for this server to edit its profile.",
                    ephemeral=True,
                )
                return

        await interaction.response.send_modal(
            EditProfileModal(
                self._bot,
                self._profile_channel_id,
                profile.display_name,
            )
        )


class EditProfileModal(discord.ui.Modal, title="Edit profile"):
    def __init__(
        self,
        bot: NetworkRelayBot,
        profile_channel_id: int,
        current_display_name: str,
    ) -> None:
        super().__init__()
        self._bot = bot
        self._profile_channel_id = profile_channel_id

        self.display_name = discord.ui.Label(
            text="Display name",
            description="Name shown on relayed messages",
            component=discord.ui.TextInput(
                default=current_display_name,
                placeholder="My Server",
                max_length=100,
                required=True,
            ),
        )
        self.profile_image = discord.ui.Label(
            text="Profile image",
            description="Upload a PNG, JPG, WebP, or GIF (optional — leave empty to keep current)",
            component=discord.ui.FileUpload(required=False, max_values=1),
        )
        self.add_item(self.display_name)
        self.add_item(self.profile_image)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("This form only works inside your server feed channel.")
            return

        context = self._bot.bot_context
        if context is None:
            await interaction.followup.send("Bot is not ready yet.")
            return

        profile = await context.profile_repo.get_by_thread_id(self._profile_channel_id)
        if profile is None:
            await interaction.followup.send("This profile is no longer registered.")
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send("Could not resolve your membership.")
            return

        if not member.guild_permissions.manage_guild:
            if profile.partner_role_id is None:
                await interaction.followup.send("This profile has no partner role configured.")
                return
            server_role = guild.get_role(profile.partner_role_id)
            if server_role is None or server_role not in member.roles:
                await interaction.followup.send(
                    "You need the partner role for this server to edit its profile."
                )
                return

        display_name = self.display_name.component.value.strip()
        raw_image: bytes | None = None
        attachments = self.profile_image.component.values
        if attachments:
            from bot.domain.errors import ProfileValidationError
            from bot.services.image_service import read_profile_image_attachment

            try:
                image = await read_profile_image_attachment(attachments[0])
            except ProfileValidationError as exc:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Profile Update Failed",
                        description=str(exc),
                        colour=discord.Colour.red(),
                    ),
                    ephemeral=True,
                )
                return
            except discord.HTTPException:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Profile Update Failed",
                        description="Failed to read the uploaded profile image.",
                        colour=discord.Colour.red(),
                    ),
                    ephemeral=True,
                )
                return
            raw_image = image.data

        result = await context.profile_sync.update_partner_profile(
            guild,
            channel,
            display_name=display_name,
            profile_image_bytes=raw_image,
            starter_view=EditProfileView(self._bot, self._profile_channel_id),
        )
        if not result.success or result.profile is None:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Profile Update Failed",
                    description=result.error or "Unknown error",
                    colour=discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Profile Updated",
            description="Your relay profile was updated.",
            colour=discord.Colour.green(),
        )
        embed.add_field(name="Display name", value=result.profile.display_name, inline=True)
        if result.warnings:
            embed.add_field(
                name="Warnings",
                value="\n".join(f"• {warning}" for warning in result.warnings),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)
