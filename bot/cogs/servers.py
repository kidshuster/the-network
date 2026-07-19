from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.client import NetworkRelayBot
from bot.cogs._autocomplete import network_key_autocomplete, server_name_autocomplete
from bot.cogs._checks import require_manage_guild
from bot.constants import DEGRADED_FALLBACK
from bot.context import BotContext
from bot.domain.errors import ProfileValidationError
from bot.domain.network import Network
from bot.domain.profile import ServerProfile
from bot.ui.profile_views import EditProfileView

logger = logging.getLogger(__name__)


@app_commands.default_permissions(manage_guild=True)
class ServerCog(
    commands.GroupCog,
    group_name="server",
    group_description="Manage participating servers on a network",
):
    def __init__(self, bot: NetworkRelayBot) -> None:
        self.bot = bot

    @require_manage_guild()
    @app_commands.command(
        name="create",
        description="Create server feed channel, access role, and pinned profile post",
    )
    @app_commands.describe(
        key="Network key (nkey)",
        server_name="Participating server name",
        profile_image="Profile image used for the relay emoji",
        display_name="Display label in relay headers",
    )
    @app_commands.autocomplete(key=network_key_autocomplete)
    async def create(
        self,
        interaction: discord.Interaction,
        key: str,
        server_name: str,
        profile_image: discord.Attachment,
        display_name: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or guild.id != self.bot.settings.guild_id:
            await interaction.followup.send(
                "This bot only operates in the configured central guild.",
                ephemeral=True,
            )
            return

        context = self._context()
        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send("Bot member is not available in this guild.")
            return

        try:
            result = await context.profile_sync.create_profile(
                guild,
                bot_member,
                server_name=server_name,
                profile_image=profile_image,
                display_name=display_name,
                network_key=key,
                enabled=True,
            )
        except Exception:
            logger.exception(
                "Server create failed",
                extra={
                    "network_key": key,
                    "server_name": server_name,
                    "user_id": interaction.user.id,
                },
            )
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Server Create Failed",
                    description="An unexpected error occurred. Check bot logs.",
                    colour=discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return

        if not result.success or result.feed_channel is None:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Server Create Failed",
                    description=result.error or "Unknown error",
                    colour=discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return

        if result.starter_message is not None and result.profile_channel is not None:
            profile_view = EditProfileView(self.bot, result.profile_channel.id)
            self.bot.add_view(profile_view)
            try:
                await result.starter_message.edit(view=profile_view)
            except discord.HTTPException:
                logger.warning(
                    "Could not attach edit profile view after server create",
                    extra={"profile_channel_id": result.profile_channel.id},
                )

        profile = result.profile
        embed = discord.Embed(
            title="Server Created",
            description=f"Feed channel: {result.feed_channel.mention}",
            colour=discord.Colour.green(),
        )
        embed.add_field(name="Network", value=f"`{key.strip().lower()}`", inline=True)
        embed.add_field(name="Server", value=server_name, inline=True)
        embed.add_field(name="Display name", value=display_name, inline=True)
        if result.server_role is not None:
            embed.add_field(
                name="Server role",
                value=result.server_role.mention,
                inline=False,
            )
        if profile is not None:
            embed.add_field(name="Emoji", value=self._emoji_label(profile), inline=False)
        if result.sync_result and result.sync_result.warnings:
            embed.add_field(
                name="Warnings",
                value="\n".join(f"• {warning}" for warning in result.sync_result.warnings),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @require_manage_guild()
    @app_commands.command(
        name="delete",
        description="Delete a server and its feed, forum, role, and profile",
    )
    @app_commands.describe(
        key="Network key (nkey)",
        server_name="Participating server name",
    )
    @app_commands.autocomplete(key=network_key_autocomplete, server_name=server_name_autocomplete)
    async def delete(
        self,
        interaction: discord.Interaction,
        key: str,
        server_name: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or guild.id != self.bot.settings.guild_id:
            await interaction.followup.send(
                "This bot only operates in the configured central guild.",
                ephemeral=True,
            )
            return

        context = self._context()
        try:
            profile = await self._require_server(context, key, server_name)
        except ProfileValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        try:
            result = await context.profile_cleanup.cleanup_server(guild, profile)
        except Exception:
            logger.exception(
                "Server delete cleanup failed",
                extra={"server_name": server_name, "network_key": key},
            )
            await interaction.followup.send(
                "Server cleanup failed. Check bot logs.",
                ephemeral=True,
            )
            return

        if result is None:
            await interaction.followup.send(
                "Server was not found or cleanup is already in progress.",
                ephemeral=True,
            )
            return

        await context.refresh_profile_counts()
        await interaction.followup.send(
            f"Server **{profile.server_name}** was deleted from network `{key.strip().lower()}`.",
            ephemeral=True,
        )

    @require_manage_guild()
    @app_commands.command(name="enable", description="Enable relaying for a server")
    @app_commands.describe(
        key="Network key (nkey)",
        server_name="Participating server name",
    )
    @app_commands.autocomplete(key=network_key_autocomplete, server_name=server_name_autocomplete)
    async def enable(
        self,
        interaction: discord.Interaction,
        key: str,
        server_name: str,
    ) -> None:
        await self._set_enabled(interaction, key, server_name, enabled=True)

    @require_manage_guild()
    @app_commands.command(name="disable", description="Disable relaying for a server")
    @app_commands.describe(
        key="Network key (nkey)",
        server_name="Participating server name",
    )
    @app_commands.autocomplete(key=network_key_autocomplete, server_name=server_name_autocomplete)
    async def disable(
        self,
        interaction: discord.Interaction,
        key: str,
        server_name: str,
    ) -> None:
        await self._set_enabled(interaction, key, server_name, enabled=False)

    @require_manage_guild()
    @app_commands.command(name="status", description="Show server status for a network")
    @app_commands.describe(key="Network key (nkey)")
    @app_commands.autocomplete(key=network_key_autocomplete)
    async def status(self, interaction: discord.Interaction, key: str) -> None:
        await interaction.response.defer(ephemeral=True)
        context = self._context()
        network = await context.network_repo.get_by_key(key)
        if network is None:
            await interaction.followup.send(
                f"Network `{key.strip().lower()}` was not found.",
                ephemeral=True,
            )
            return

        profiles = await context.profile_repo.list_by_network_id(network.id)
        if not profiles:
            await interaction.followup.send(
                f"No servers registered on network `{network.key}` yet.",
                ephemeral=True,
            )
            return

        enabled_count = sum(1 for profile in profiles if profile.enabled)
        embed = discord.Embed(
            title=f"Server Status — {network.display_name}",
            description=f"Network `{network.key}`",
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="Registered", value=str(len(profiles)), inline=True)
        embed.add_field(name="Enabled", value=str(enabled_count), inline=True)
        embed.add_field(name="Disabled", value=str(len(profiles) - enabled_count), inline=True)

        for profile in profiles[:25]:
            status = "enabled" if profile.enabled else "disabled"
            embed.add_field(
                name=profile.server_name,
                value=(
                    f"Status: **{status}**\n"
                    f"Display: {profile.display_name}\n"
                    f"Feed: <#{profile.source_channel_id}>\n"
                    f"Emoji: {self._emoji_label(profile)}"
                ),
                inline=False,
            )
        if len(profiles) > 25:
            embed.set_footer(text=f"Showing 25 of {len(profiles)} servers.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @require_manage_guild()
    @app_commands.command(name="list", description="List servers on one network or all networks")
    @app_commands.describe(key="Optional network key (nkey)")
    @app_commands.autocomplete(key=network_key_autocomplete)
    async def list_servers(
        self,
        interaction: discord.Interaction,
        key: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        context = self._context()
        networks = {
            network.id: network for network in await context.network_repo.list_all()
        }

        if key is not None:
            network = await context.network_repo.get_by_key(key)
            if network is None:
                await interaction.followup.send(
                    f"Network `{key.strip().lower()}` was not found.",
                    ephemeral=True,
                )
                return
            profiles = await context.profile_repo.list_by_network_id(network.id)
            title = f"Servers — {network.display_name}"
        else:
            profiles = await context.profile_repo.list_all()
            title = "Servers"

        if not profiles:
            await interaction.followup.send("No servers configured yet.", ephemeral=True)
            return

        embed = discord.Embed(title=title, colour=discord.Colour.blurple())
        for profile in profiles[:25]:
            network = networks.get(profile.network_id)
            network_key = network.key if network else str(profile.network_id)
            status = "enabled" if profile.enabled else "disabled"
            embed.add_field(
                name=f"{profile.display_name} ({profile.server_name})",
                value=(
                    f"Status: **{status}**\n"
                    f"Network: `{network_key}`\n"
                    f"Feed: <#{profile.source_channel_id}>\n"
                    f"Emoji: {self._emoji_label(profile)}"
                ),
                inline=False,
            )
        if len(profiles) > 25:
            embed.set_footer(text=f"Showing 25 of {len(profiles)} servers.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _set_enabled(
        self,
        interaction: discord.Interaction,
        key: str,
        server_name: str,
        *,
        enabled: bool,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        context = self._context()
        try:
            network = await self._require_network(context, key)
            profile = await context.profile_repo.set_enabled_by_network_and_server_name(
                network.id,
                server_name,
                enabled,
            )
            await context.refresh_profile_counts()
        except ProfileValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        state = "enabled" if profile.enabled else "disabled"
        await interaction.followup.send(
            f"Server **{profile.server_name}** on `{network.key}` is now **{state}**.",
            ephemeral=True,
        )

    async def _require_network(self, context: BotContext, key: str) -> Network:
        network = await context.network_repo.get_by_key(key)
        if network is None:
            raise ProfileValidationError(f"Network `{key.strip().lower()}` was not found.")
        return network

    async def _require_server(
        self,
        context: BotContext,
        key: str,
        server_name: str,
    ) -> ServerProfile:
        network = await self._require_network(context, key)
        profile = await context.profile_repo.get_by_network_and_server_name(
            network.id,
            server_name,
        )
        if profile is None:
            raise ProfileValidationError(
                f"No server {server_name!r} found on network `{network.key}`."
            )
        return profile

    def _emoji_label(self, profile: ServerProfile) -> str:
        if profile.degraded_reason:
            return f"{DEGRADED_FALLBACK} degraded — {profile.degraded_reason}"
        if profile.emoji_id and profile.emoji_name:
            return f"<:{profile.emoji_name}:{profile.emoji_id}>"
        return "not set"

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != self.bot.settings.guild_id:
            return
        context = self.bot.bot_context
        if context is None:
            return
        try:
            cleanup = context.profile_cleanup
            if isinstance(channel, discord.CategoryChannel):
                await cleanup.cleanup_by_profile_category_id(channel.guild, channel.id)
                return
            profile = await context.profile_repo.get_by_source_channel(channel.id)
            if profile is not None:
                await cleanup.cleanup_by_feed_channel_id(channel.guild, channel.id)
                return
            await cleanup.cleanup_by_profile_channel_id(channel.guild, channel.id)
        except Exception:
            logger.exception(
                "Server cleanup failed after channel delete",
                extra={"channel_id": channel.id},
            )

    def _context(self) -> BotContext:
        if self.bot.bot_context is None:
            raise RuntimeError("Bot context is not initialized")
        return self.bot.bot_context


async def setup(bot: NetworkRelayBot) -> None:
    await bot.add_cog(ServerCog(bot))
