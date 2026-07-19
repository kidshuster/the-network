from __future__ import annotations

import asyncio
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
from bot.services.guild_channels import resolve_network_join_channel
from bot.services.guild_init import GuildInitResult, initialize_guild
from bot.services.join_requests_sticky import sync_network_how_to_join_sticky
from bot.services.network_provision import (
    NetworkProvisionService,
    resolve_access_role,
)
from bot.services.network_validation import validate_network_channels
from bot.services.rules_sticky import sync_rules_sticky
from bot.ui.join_views import JoinServerView

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)

_MAX_INIT_FIELD_ITEMS = 8
_MAX_INIT_FIELD_CHARS = 900


def _guild_init_embed(result: GuildInitResult) -> discord.Embed:
    if not result.success:
        return discord.Embed(
            title="Guild Init Failed",
            description=result.reason or "Unknown error",
            colour=discord.Colour.red(),
        )

    embed = discord.Embed(
        title="Guild Initialized",
        description="Hub layout is ready. Run `/network create` next.",
        colour=discord.Colour.green(),
    )
    if result.created_categories:
        names = result.created_categories[:_MAX_INIT_FIELD_ITEMS]
        embed.add_field(
            name="Categories created",
            value="\n".join(f"• {name}" for name in names),
            inline=False,
        )
    if result.created_channels:
        names = result.created_channels[:_MAX_INIT_FIELD_ITEMS]
        embed.add_field(
            name="Channels created",
            value="\n".join(f"• {name}" for name in names),
            inline=False,
        )
    if result.moved_channels:
        embed.add_field(
            name="Channels moved",
            value="\n".join(f"• {item}" for item in result.moved_channels[:_MAX_INIT_FIELD_ITEMS]),
            inline=False,
        )
    if result.updated_roles:
        embed.add_field(
            name="Roles",
            value="\n".join(f"• {item}" for item in result.updated_roles[:_MAX_INIT_FIELD_ITEMS]),
            inline=False,
        )
    if result.failed_steps:
        embed.colour = discord.Colour.gold()
        embed.description = (
            "Hub layout sync finished with warnings. Review the notes below, "
            "then run `/network create` if categories look correct."
        )
        warnings = "\n".join(
            f"• {step}" for step in result.failed_steps[:_MAX_INIT_FIELD_ITEMS]
        )
        if len(result.failed_steps) > _MAX_INIT_FIELD_ITEMS:
            warnings += f"\n• …and {len(result.failed_steps) - _MAX_INIT_FIELD_ITEMS} more"
        embed.add_field(
            name="Permission warnings",
            value=warnings[:_MAX_INIT_FIELD_CHARS],
            inline=False,
        )
    if result.notes:
        notes = "\n".join(f"• {note}" for note in result.notes[:_MAX_INIT_FIELD_ITEMS])
        if len(result.notes) > _MAX_INIT_FIELD_ITEMS:
            notes += f"\n• …and {len(result.notes) - _MAX_INIT_FIELD_ITEMS} more"
        embed.add_field(name="Notes", value=notes[:_MAX_INIT_FIELD_CHARS], inline=False)
    return embed


@app_commands.default_permissions(manage_guild=True)
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
        name="sync-how-to-join",
        description="Clear a network join channel and repost the public join guide",
    )
    @app_commands.describe(key="Network key (nkey)")
    @app_commands.autocomplete(key=network_key_autocomplete)
    async def sync_how_to_join(self, interaction: discord.Interaction, key: str) -> None:
        await interaction.response.defer(ephemeral=True)
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

        context = self._context()
        network = await context.network_repo.get_by_key(key)
        if network is None:
            await interaction.followup.send(
                f"Network `{key.strip().lower()}` was not found.",
                ephemeral=True,
            )
            return

        channel = resolve_network_join_channel(guild, network)
        if channel is None and isinstance(interaction.channel, discord.TextChannel):
            channel = interaction.channel
        if channel is None:
            await interaction.followup.send(
                "No join channel found for this network. Run the command in a text channel "
                "or recreate the network so a join channel is provisioned.",
                ephemeral=True,
            )
            return

        result = await sync_network_how_to_join_sticky(
            guild,
            bot_member,
            network,
            self.bot,
            get_setting=context.settings_repo.get,
            set_setting=context.settings_repo.set,
            channel=channel,
            wipe_channel=True,
        )
        if not result.success:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Sync How-To-Join Failed",
                    description=result.reason or "Unknown error",
                    colour=discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="How-To-Join Synced",
            description=(
                f"Cleared {channel.mention} and posted the join guide "
                f"for **{network.display_name}**."
            ),
            colour=discord.Colour.green(),
        )
        if result.message is not None:
            embed.add_field(name="Message", value=result.message.jump_url, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @require_manage_guild()
    @app_commands.command(
        name="sync-rules",
        description="Clear the rules channel and repost hub relay rules",
    )
    async def sync_rules(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
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

        context = self._context()
        result = await sync_rules_sticky(
            guild,
            bot_member,
            get_setting=context.settings_repo.get,
            set_setting=context.settings_repo.set,
        )
        if not result.success:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Sync Rules Failed",
                    description=result.reason or "Unknown error",
                    colour=discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Hub Rules Synced",
            description="Cleared the rules channel and posted the relay rules.",
            colour=discord.Colour.green(),
        )
        if result.message is not None:
            embed.add_field(name="Message", value=result.message.jump_url, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @require_manage_guild()
    @app_commands.command(
        name="init",
        description="Set up hub categories, channels, roles, and permissions on a blank guild",
    )
    async def init_guild(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
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

        await interaction.followup.send(
            "Guild init started — syncing categories and permissions. "
            "You'll get another message when it finishes (usually under a minute).",
            ephemeral=True,
        )

        async def _run_init() -> None:
            try:
                profiles = None
                if self.bot.bot_context is not None:
                    profiles = await self.bot.bot_context.profile_repo.list_all()
                result = await initialize_guild(
                    guild,
                    bot_member,
                    access_role_name=self.bot.settings.network_access_role_name,
                    moderator_role_name=self.bot.settings.network_moderator_role_name,
                    profiles=profiles,
                )
                await interaction.followup.send(
                    embed=_guild_init_embed(result),
                    ephemeral=True,
                )
            except Exception:
                logger.exception("Guild init failed unexpectedly")
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Guild Init Failed",
                        description="An unexpected error occurred. Check bot logs for details.",
                        colour=discord.Colour.red(),
                    ),
                    ephemeral=True,
                )

        asyncio.create_task(_run_init())

    @require_manage_guild()
    @app_commands.command(
        name="create",
        description="Create network feed category and register a relay network",
    )
    @app_commands.describe(
        key="Network key (nkey)",
        name="Human-readable network name",
        announcement_channel=(
            "Announcement channel for published relays (optional — created automatically "
            "under Subscribe To Me! if omitted)"
        ),
    )
    async def create(
        self,
        interaction: discord.Interaction,
        key: str,
        name: str,
        announcement_channel: discord.abc.GuildChannel | None = None,
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
            output_channel: discord.abc.GuildChannel | None
            if announcement_channel is None:
                output_channel = None
            elif getattr(announcement_channel, "type", None) is discord.ChannelType.news:
                output_channel = announcement_channel
            else:
                raise NetworkValidationError(
                    f"{announcement_channel.mention} must be an announcement channel."
                )
            channels = await self._provision.provision(
                guild,
                bot_member,
                key=key,
                display_name=name,
                output_channel=output_channel,
                access_role=role,
            )
            output_channel = channels.output_channel
            await validate_network_channels(
                guild,
                bot_member,
                channels.feed_category,
                output_channel,
                None,
            )
            network = await context.network_repo.create(
                guild_id=guild.id,
                key=key,
                display_name=name,
                feed_category_id=channels.feed_category.id,
                output_channel_id=output_channel.id,
                concat_channel_id=None,
                profile_forum_channel_id=None,
                join_channel_id=channels.join_channel.id,
            )
            await context.routing_service.load_cache()
            await context.refresh_network_counts()
            rules_result = await sync_rules_sticky(
                guild,
                bot_member,
                get_setting=context.settings_repo.get,
                set_setting=context.settings_repo.set,
            )
            how_to_join_result = await sync_network_how_to_join_sticky(
                guild,
                bot_member,
                network,
                self.bot,
                get_setting=context.settings_repo.get,
                set_setting=context.settings_repo.set,
                channel=channels.join_channel,
                wipe_channel=True,
            )
            self.bot.add_view(JoinServerView(self.bot, network.key))
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
        except Exception:
            logger.exception(
                "Network create failed unexpectedly",
                extra={"user_id": interaction.user.id, "channel_id": interaction.channel_id},
            )
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Network Create Failed",
                    description="An unexpected error occurred. Check bot logs for details.",
                    colour=discord.Colour.red(),
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(title="Network Created", colour=discord.Colour.green())
        embed.add_field(name="Key", value=f"`{network.key}`", inline=True)
        embed.add_field(name="Name", value=network.display_name, inline=True)
        embed.add_field(name="Feed category", value=channels.feed_category.mention, inline=False)
        output_label = output_channel.mention
        if channels.created_output_channel:
            output_label = f"{output_channel.mention} (created)"
        embed.add_field(name="Output", value=output_label, inline=False)
        embed.add_field(name="Join channel", value=channels.join_channel.mention, inline=False)
        embed.add_field(name="Access role", value=role.mention, inline=False)
        embed.add_field(
            name="Next steps",
            value=(
                f"1. Partners follow {channels.join_channel.mention} and click **Join Server**, "
                "or use `/server create` for admins.\n"
                "2. Each approved server gets one channel under the feed category with a "
                "pinned profile and relay feed.\n"
                "3. Point Channel Follow from partner announcement channels into that channel."
            ),
            inline=False,
        )
        if rules_result.skipped and rules_result.reason:
            embed.add_field(
                name="Hub rules",
                value=f"Not posted: {rules_result.reason}",
                inline=False,
            )
        elif rules_result.message is not None:
            embed.add_field(
                name="Hub rules",
                value=f"Guidelines posted in {rules_result.message.jump_url}",
                inline=False,
            )
        if how_to_join_result.skipped and how_to_join_result.reason:
            embed.add_field(
                name="How-to-join guide",
                value=f"Not posted: {how_to_join_result.reason}",
                inline=False,
            )
        elif how_to_join_result.message is not None:
            action = "updated" if how_to_join_result.updated else "already current"
            embed.add_field(
                name="How-to-join guide",
                value=f"Guide {action} in {how_to_join_result.message.jump_url}",
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
        deleted_categories = 0
        deleted_roles = 0
        try:
            network = await context.network_repo.get_by_key(key)
            if network is None:
                raise NetworkValidationError(f"Network `{key.strip().lower()}` was not found.")

            cleanup = await context.network_cleanup.cleanup_network(guild, network)
            deleted_servers = cleanup.deleted_servers
            deleted_channels = cleanup.deleted_channels
            deleted_categories = cleanup.deleted_categories
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
            await context.server_request_repo.delete_by_network_id(network.id)
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
        if deleted_categories:
            parts.append(f"**{deleted_categories}** categor(ies) removed.")
        if deleted_roles:
            parts.append(f"**{deleted_roles}** server role(s) removed.")
        parts.append("The announcement output channel was kept.")
        await interaction.followup.send(" ".join(parts), ephemeral=True)
        logger.info(
            "Network deleted",
            extra={
                "network_key": network.key,
                "user_id": interaction.user.id,
                "deleted_servers": deleted_servers,
                "deleted_channels": deleted_channels,
                "deleted_categories": deleted_categories,
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
