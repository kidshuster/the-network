from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.client import NetworkRelayBot
from bot.cogs._checks import require_manage_guild
from bot.context import BotContext
from bot.domain.errors import NetworkValidationError
from bot.messages import render_embed, render_text
from bot.services.guild_init import GuildInitResult, initialize_guild
from bot.services.guild_layout import resolve_join_the_network_channel
from bot.services.guild_uninit import GuildUninitResult, uninitialize_guild
from bot.services.hub_data_reset import reset_hub_layout_data
from bot.services.join_requests_sticky import sync_hub_join_sticky
from bot.ui.join_views import JoinNetworkView

logger = logging.getLogger(__name__)

_MAX_INIT_FIELD_ITEMS = 8
_MAX_INIT_FIELD_CHARS = 900


def _append_bullet_field(
    embed: discord.Embed,
    *,
    name: str,
    items: list[str],
) -> None:
    if not items:
        return
    embed.add_field(
        name=name,
        value="\n".join(f"• {item}" for item in items[:_MAX_INIT_FIELD_ITEMS]),
        inline=False,
    )


def _server_init_embed(result: GuildInitResult) -> discord.Embed:
    if not result.success:
        return render_embed(
            "server_init_failed",
            description=result.reason or "Unknown error",
        )

    embed = render_embed("server_init_success")
    _append_bullet_field(embed, name="Categories created", items=result.created_categories)
    _append_bullet_field(embed, name="Channels created", items=result.created_channels)
    _append_bullet_field(embed, name="Channels moved", items=result.moved_channels)
    _append_bullet_field(embed, name="Roles", items=result.updated_roles)
    if result.failed_steps:
        embed.colour = discord.Colour.gold()
        embed.add_field(
            name="Permission warnings",
            value="\n".join(f"• {step}" for step in result.failed_steps[:_MAX_INIT_FIELD_ITEMS])[
                :_MAX_INIT_FIELD_CHARS
            ],
            inline=False,
        )
    if result.notes:
        embed.add_field(
            name="Notes",
            value="\n".join(f"• {note}" for note in result.notes[:_MAX_INIT_FIELD_ITEMS])[
                :_MAX_INIT_FIELD_CHARS
            ],
            inline=False,
        )
    return embed


def _server_uninit_embed(result: GuildUninitResult) -> discord.Embed:
    if not result.success:
        return render_embed(
            "server_uninit_failed",
            description=result.reason or "Unknown error",
        )
    embed = render_embed("server_uninit_success")
    for field_name, items in (
        ("Categories deleted", result.deleted_categories),
        ("Channels deleted", result.deleted_channels),
        ("Roles deleted", result.deleted_roles),
        ("Preserved", result.preserved_channels),
    ):
        _append_bullet_field(embed, name=field_name, items=items)
    if result.notes:
        embed.add_field(
            name="Notes",
            value="\n".join(f"• {note}" for note in result.notes[:_MAX_INIT_FIELD_ITEMS])[
                :_MAX_INIT_FIELD_CHARS
            ],
            inline=False,
        )
    return embed


@app_commands.default_permissions(manage_guild=True)
class ServerCog(
    commands.GroupCog,
    group_name="server",
    group_description="Initialize the Discord hub server layout",
):
    def __init__(self, bot: NetworkRelayBot) -> None:
        self.bot = bot

    @require_manage_guild()
    @app_commands.command(
        name="init",
        description="Set up hub categories/channels and run permission smoke checks",
    )
    async def init_server(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or guild.id != self.bot.settings.guild_id:
            await interaction.followup.send(render_text("central_guild_only"), ephemeral=True)
            return

        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send(render_text("bot_member_unavailable"), ephemeral=True)
            return

        await interaction.followup.send(render_text("server_init_started"), ephemeral=True)

        async def _run() -> None:
            try:
                clients = None
                if self.bot.bot_context is not None:
                    clients = await self.bot.bot_context.client_repo.list_all()
                result = await initialize_guild(
                    guild,
                    bot_member,
                    access_role_name=self.bot.settings.network_access_role_name,
                    operator_role_name=self.bot.settings.network_operator_role_name,
                    clients=clients,
                    bot=self.bot,
                    context=self.bot.bot_context,
                )
                await interaction.followup.send(
                    embed=_server_init_embed(result),
                    ephemeral=True,
                )
            except NetworkValidationError as exc:
                await interaction.followup.send(
                    embed=render_embed("server_init_failed", description=str(exc)),
                    ephemeral=True,
                )
            except Exception as exc:
                logger.exception("Server init failed unexpectedly")
                await interaction.followup.send(
                    embed=render_embed(
                        "server_init_failed",
                        description=f"Unexpected error: {type(exc).__name__}: {exc}",
                    ),
                    ephemeral=True,
                )

        asyncio.create_task(_run())

    @require_manage_guild()
    @app_commands.command(
        name="uninit",
        description="Remove hub categories/channels/roles (keeps #rules and #moderator-only)",
    )
    async def uninit_server(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or guild.id != self.bot.settings.guild_id:
            await interaction.followup.send(render_text("central_guild_only"), ephemeral=True)
            return

        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send(render_text("bot_member_unavailable"), ephemeral=True)
            return

        await interaction.followup.send(render_text("server_uninit_started"), ephemeral=True)

        async def _run() -> None:
            try:
                result = await uninitialize_guild(
                    guild,
                    bot_member,
                    access_role_name=self.bot.settings.network_access_role_name,
                    operator_role_name=self.bot.settings.network_operator_role_name,
                )
                context = self.bot.bot_context
                if context is not None:
                    try:
                        data_result = await reset_hub_layout_data(context, guild.id)
                        note = data_result.summary_note()
                        if note is not None:
                            result.notes.append(note)
                    except Exception:
                        logger.exception("Hub database reset failed during server uninit")
                        result.notes.append(
                            "Could not clear hub database (networks/clients) — check bot logs."
                        )
                await interaction.followup.send(
                    embed=_server_uninit_embed(result),
                    ephemeral=True,
                )
            except Exception:
                logger.exception("Server uninit failed unexpectedly")
                await interaction.followup.send(
                    embed=render_embed(
                        "server_uninit_failed",
                        description="An unexpected error occurred. Check bot logs.",
                    ),
                    ephemeral=True,
                )

        asyncio.create_task(_run())

    @require_manage_guild()
    @app_commands.command(
        name="sync-join-guide",
        description="Refresh the join guide in #join-the-network",
    )
    async def sync_join_guide(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or guild.id != self.bot.settings.guild_id:
            await interaction.followup.send(render_text("central_guild_only"), ephemeral=True)
            return

        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send(render_text("bot_member_unavailable_short"), ephemeral=True)
            return

        context = self._context()
        channel = resolve_join_the_network_channel(guild)
        if channel is None:
            await interaction.followup.send(render_text("join_channel_missing"), ephemeral=True)
            return

        result = await sync_hub_join_sticky(
            guild,
            bot_member,
            self.bot,
            channel,
            get_setting=context.settings_repo.get,
            set_setting=context.settings_repo.set,
            wipe_channel=True,
        )
        if not result.success:
            await interaction.followup.send(
                embed=render_embed(
                    "sync_join_guide_failed",
                    description=result.reason or "Unknown error",
                ),
                ephemeral=True,
            )
            return

        self.bot.add_view(JoinNetworkView(self.bot))
        message_url = result.message.jump_url if result.message is not None else ""
        await interaction.followup.send(
            embed=render_embed(
                "sync_join_guide_success",
                channel_mention=channel.mention,
                message_url=message_url,
            ),
            ephemeral=True,
        )

    def _context(self) -> BotContext:
        if self.bot.bot_context is None:
            raise RuntimeError("Bot context is not initialized")
        return self.bot.bot_context


async def setup(bot: NetworkRelayBot) -> None:
    await bot.add_cog(ServerCog(bot))
