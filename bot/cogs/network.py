from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.client import NetworkRelayBot
from bot.cogs._autocomplete import network_key_autocomplete
from bot.cogs._checks import require_manage_guild
from bot.context import BotContext
from bot.domain.errors import NetworkValidationError
from bot.services.discord_errors import DiscordStepError, format_discord_step_error
from bot.services.network_provision import (
    NetworkProvisionService,
    create_guide_thread,
    resolve_access_role,
)
from bot.services.network_validation import validate_network_channels

logger = logging.getLogger(__name__)


class NetworkCog(
    commands.GroupCog,
    group_name="network",
    group_description="Manage relay networks",
):
    def __init__(self, bot: NetworkRelayBot) -> None:
        self.bot = bot
        self._provision = NetworkProvisionService()

    @require_manage_guild()
    @app_commands.command(
        name="create",
        description="Create network infrastructure and register a relay network",
    )
    @app_commands.describe(
        key="Network key (nkey)",
        name="Human-readable network name",
        announcement_channel="Announcement channel for published relays",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        key: str,
        name: str,
        announcement_channel: discord.abc.GuildChannel,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        context = self._context()
        guild = interaction.guild
        if guild is None or guild.id != self.bot.settings.guild_id:
            await interaction.followup.send(
                "This bot only operates in the configured central guild.",
                ephemeral=True,
            )
            return

        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send("Bot member is not available in this guild.")
            return

        try:
            role = resolve_access_role(
                guild,
                role_name=self.bot.settings.network_access_role_name,
            )
            channels = await self._provision.provision(
                guild,
                bot_member,
                key=key,
                display_name=name,
                output_channel=announcement_channel,
                access_role=role,
            )
            await validate_network_channels(
                guild,
                bot_member,
                channels.category,
                announcement_channel,
                None,
            )
            network = await context.network_repo.create(
                guild_id=guild.id,
                key=key,
                display_name=name,
                feed_category_id=channels.category.id,
                output_channel_id=announcement_channel.id,
                concat_channel_id=None,
                profile_forum_channel_id=channels.profile_forum.id,
            )
            await context.routing_service.load_cache()
            await context.refresh_network_counts()
            guide_thread = await create_guide_thread(
                channels.profile_forum,
                network=network,
            )
        except NetworkValidationError as exc:
            embed = discord.Embed(
                title="Network Create Failed",
                description=str(exc),
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        except DiscordStepError as exc:
            logger.warning(
                "Network create Discord step failed",
                extra={
                    "step": exc.step,
                    "status": exc.exc.status,
                    "code": getattr(exc.exc, "code", None),
                    "user_id": interaction.user.id,
                    "channel_id": interaction.channel_id,
                },
            )
            embed = discord.Embed(
                title="Network Create Failed",
                description=format_discord_step_error(exc.step, exc.exc),
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        except discord.HTTPException as exc:
            logger.warning(
                "Network create Discord API failed",
                extra={
                    "status": exc.status,
                    "code": getattr(exc, "code", None),
                    "user_id": interaction.user.id,
                    "channel_id": interaction.channel_id,
                },
            )
            embed = discord.Embed(
                title="Network Create Failed",
                description=format_discord_step_error("network create", exc),
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(title="Network Created", colour=discord.Colour.green())
        embed.add_field(name="Key", value=f"`{network.key}`", inline=True)
        embed.add_field(name="Name", value=network.display_name, inline=True)
        embed.add_field(name="Feed category", value=channels.category.mention, inline=False)
        embed.add_field(name="Profile forum", value=channels.profile_forum.mention, inline=False)
        embed.add_field(name="Output", value=announcement_channel.mention, inline=False)
        embed.add_field(name="Access role", value=role.mention, inline=False)
        embed.add_field(
            name="Next steps",
            value=(
                f"1. Add servers with `/server create` (network `{network.key}`).\n"
                "2. Point Channel Follow from partner announcement channels into each "
                "server's feed channel.\n"
                f"3. Guide thread: {guide_thread.jump_url}"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(
            "Network created",
            extra={
                "network_key": network.key,
                "network_id": network.id,
                "user_id": interaction.user.id,
            },
        )

    @require_manage_guild()
    @app_commands.command(name="delete", description="Delete a network record")
    @app_commands.describe(key="Network key (nkey)")
    @app_commands.autocomplete(key=network_key_autocomplete)
    async def delete(self, interaction: discord.Interaction, key: str) -> None:
        await interaction.response.defer(ephemeral=True)
        context = self._context()
        guild = interaction.guild
        if guild is None or guild.id != self.bot.settings.guild_id:
            await interaction.followup.send(
                "This bot only operates in the configured central guild.",
                ephemeral=True,
            )
            return

        deleted_servers = 0
        deleted_channels = 0
        deleted_category = False
        deleted_roles = 0
        try:
            network = await context.network_repo.get_by_key(key)
            if network is None:
                raise NetworkValidationError(f"Network `{key.strip().lower()}` was not found.")

            cleanup = await context.network_cleanup.cleanup_network(guild, network)
            deleted_servers = cleanup.deleted_servers
            deleted_channels = cleanup.deleted_channels
            deleted_category = cleanup.deleted_category
            deleted_roles = cleanup.deleted_roles
            await context.refresh_profile_counts()

            remaining = await context.profile_repo.list_by_network_id(network.id)
            if remaining:
                names = ", ".join(f"`{profile.server_name}`" for profile in remaining[:10])
                extra = f" (+{len(remaining) - 10} more)" if len(remaining) > 10 else ""
                raise NetworkValidationError(
                    "Network delete stopped because some servers could not be removed: "
                    f"{names}{extra}"
                )

            await context.relay_record_repo.delete_by_network_id(network.id)
            await context.network_repo.delete(key)
            await context.routing_service.load_cache()
            await context.refresh_network_counts()
        except NetworkValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception:
            logger.exception(
                "Network delete failed",
                extra={"network_key": key, "user_id": interaction.user.id},
            )
            await interaction.followup.send(
                "Network delete failed due to an unexpected error. Check bot logs for details.",
                ephemeral=True,
            )
            return

        parts = [f"Network `{network.key}` was deleted."]
        if deleted_servers:
            parts.append(f"**{deleted_servers}** server(s) removed.")
        if deleted_channels:
            parts.append(f"**{deleted_channels}** channel(s) removed.")
        if deleted_category:
            parts.append("Feed category removed.")
        if deleted_roles:
            parts.append(f"**{deleted_roles}** partner role(s) removed.")
        parts.append("The announcement output channel was kept.")
        await interaction.followup.send(" ".join(parts), ephemeral=True)
        logger.info(
            "Network deleted",
            extra={
                "network_key": network.key,
                "user_id": interaction.user.id,
                "deleted_servers": deleted_servers,
                "deleted_channels": deleted_channels,
                "deleted_category": deleted_category,
                "deleted_roles": deleted_roles,
            },
        )

    @require_manage_guild()
    @app_commands.command(name="status", description="Show bot and network status")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        guild = self.bot.get_guild(self.bot.settings.guild_id)
        guild_ok = guild is not None
        guild_name = guild.name if guild else "unknown"
        latency_ms = round(self.bot.latency * 1000)

        context = self._context()
        await context.refresh_network_counts()
        await context.refresh_profile_counts()
        networks = await context.network_repo.list_all()
        enabled_networks = sum(1 for network in networks if network.enabled)

        embed = discord.Embed(
            title="Network Status",
            colour=discord.Colour.green() if guild_ok else discord.Colour.red(),
        )
        embed.add_field(
            name="Connectivity",
            value=f"Discord: connected\nLatency: {latency_ms}ms",
            inline=False,
        )
        embed.add_field(
            name="Guild",
            value=(
                f"Name: {guild_name}\n"
                f"ID: `{self.bot.settings.guild_id}`\n"
                f"Validation: {'OK' if guild_ok else 'FAILED'}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Database",
            value=(
                f"Path: `{self.bot.settings.database_path}`\n"
                f"Schema version: {self.bot.schema_version}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Networks",
            value=(
                f"Configured: {len(networks)}\n"
                f"Enabled: {enabled_networks}\n"
                f"Loaded in cache: {context.network_count}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Servers",
            value=(
                f"Registered: {context.profile_count}\n"
                f"Enabled: {context.enabled_profile_count}"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Uptime {context.uptime_label()}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @require_manage_guild()
    @app_commands.command(name="list", description="List all configured networks")
    async def list_networks(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        context = self._context()
        networks = await context.network_repo.list_all()

        if not networks:
            await interaction.followup.send("No networks configured yet.", ephemeral=True)
            return

        embed = discord.Embed(title="Networks", colour=discord.Colour.blurple())
        for network in networks:
            status = "enabled" if network.enabled else "disabled"
            server_count = len(await context.profile_repo.list_by_network_id(network.id))
            embed.add_field(
                name=f"{network.display_name} (`{network.key}`)",
                value=(
                    f"Status: **{status}**\n"
                    f"Servers: **{server_count}**\n"
                    f"Feed category: <#{network.feed_category_id}>\n"
                    f"Output: <#{network.output_channel_id}>"
                ),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    def _context(self) -> BotContext:
        if self.bot.bot_context is None:
            raise RuntimeError("Bot context is not initialized")
        return self.bot.bot_context


async def setup(bot: NetworkRelayBot) -> None:
    await bot.add_cog(NetworkCog(bot))
