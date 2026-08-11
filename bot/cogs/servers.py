from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.client import NetworkRelayBot
from bot.cogs._checks import require_manage_guild
from bot.core.hub.result import GuildInitResult
from bot.messages import render_embed, render_text
from bot.recipes import RecipeRegistryError
from bot.recipes.hub.uninitialize import GuildUninitResult

logger = logging.getLogger(__name__)

_MAX_EMBED_FIELD_CHARS = 1024
_MAX_EMBED_FIELDS = 25


def _format_bullet_list(items: list[str], *, max_items: int = 25) -> str:
    lines: list[str] = []
    for item in items[:max_items]:
        line = f"• {item}"
        candidate = "\n".join([*lines, line]) if lines else line
        if len(candidate) > _MAX_EMBED_FIELD_CHARS:
            omitted = len(items) - len(lines)
            if omitted > 0 and lines:
                lines.append(f"• … and {omitted} more")
            break
        lines.append(line)
    return "\n".join(lines)[:_MAX_EMBED_FIELD_CHARS]


def _append_bullet_field(
    embed: discord.Embed,
    *,
    name: str,
    items: list[str],
) -> None:
    if not items:
        return
    if len(embed.fields) >= _MAX_EMBED_FIELDS:
        return
    embed.add_field(
        name=name,
        value=_format_bullet_list(items),
        inline=False,
    )


def _server_init_rectification_embeds(result: GuildInitResult) -> list[discord.Embed]:
    if not result.success:
        return []

    has_work = bool(
        result.rectifications or result.rectification_skipped or result.rectification_failures
    )
    if not has_work:
        embed = render_embed("server_init_rectification")
        embed.description = (
            "Existing client profiles and Leaders channels were checked. "
            "No registered clients needed permission rectification."
        )
        return [embed]

    embeds: list[discord.Embed] = []
    base = render_embed("server_init_rectification")
    embeds.append(base)
    current = base

    def _ensure_embed() -> discord.Embed:
        nonlocal current
        if len(current.fields) >= _MAX_EMBED_FIELDS:
            current = render_embed("server_init_rectification")
            current.description = "Rectification report (continued)."
            embeds.append(current)
        return current

    for item in result.rectifications:
        target = _ensure_embed()
        _append_bullet_field(target, name="Rectified", items=[item])

    for item in result.rectification_skipped:
        target = _ensure_embed()
        _append_bullet_field(target, name="Skipped", items=[item])

    for item in result.rectification_failures:
        target = _ensure_embed()
        target.colour = discord.Colour.gold()
        _append_bullet_field(target, name="Rectification warnings", items=[item])

    if not result.rectifications and not result.rectification_failures:
        base.description = (
            "Existing client profiles and Leaders channels were checked. "
            "Some profiles could not be rectified — see Skipped below."
        )

    return embeds


def _server_init_rectification_embed(result: GuildInitResult) -> discord.Embed | None:
    embeds = _server_init_rectification_embeds(result)
    return embeds[0] if embeds else None


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
    if result.notes:
        embed.add_field(
            name="Notes",
            value=_format_bullet_list(result.notes),
            inline=False,
        )
    if result.failed_steps:
        embed.colour = discord.Colour.gold()
        embed.add_field(
            name="Permission warnings",
            value=_format_bullet_list(result.failed_steps),
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
            value=_format_bullet_list(result.notes),
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

    async def _run(self, interaction: discord.Interaction, name: str) -> object | None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or guild.id != self.bot.settings.guild_id:
            await interaction.followup.send(render_text("central_guild_only"), ephemeral=True)
            return None
        if guild.me is None:
            await interaction.followup.send(render_text("bot_member_unavailable"), ephemeral=True)
            return None
        try:
            result: object = await self.bot.recipe_registry.run(name, interaction=interaction)
            return result
        except RecipeRegistryError as exc:
            logger.exception("Command recipe failed", extra={"recipe": name})
            await interaction.followup.send(str(exc), ephemeral=True)
            return None

    @require_manage_guild()
    @app_commands.command(
        name="init",
        description="Set up hub categories/channels and run permission smoke checks",
    )
    async def init_server(self, interaction: discord.Interaction) -> None:
        result = await self._run(interaction, "server.init")
        if not isinstance(result, GuildInitResult):
            return
        await interaction.followup.send(embed=_server_init_embed(result), ephemeral=True)
        for embed in _server_init_rectification_embeds(result):
            await interaction.followup.send(embed=embed, ephemeral=True)

    @require_manage_guild()
    @app_commands.command(
        name="uninit",
        description="Remove hub categories/channels/roles (keeps #rules and #moderator-only)",
    )
    async def uninit_server(self, interaction: discord.Interaction) -> None:
        result = await self._run(interaction, "server.uninit")
        if isinstance(result, GuildUninitResult):
            await interaction.followup.send(embed=_server_uninit_embed(result), ephemeral=True)

    @require_manage_guild()
    @app_commands.command(
        name="sync-join-guide",
        description="Refresh the join guide in #join-the-network",
    )
    async def sync_join_guide(self, interaction: discord.Interaction) -> None:
        value = await self._run(interaction, "server.sync_join_guide")
        if not isinstance(value, tuple):
            return
        result, channel = value
        if not result.success:
            await interaction.followup.send(result.reason or "Unknown error", ephemeral=True)
            return
        await interaction.followup.send(
            embed=render_embed(
                "sync_join_guide_success",
                channel_mention=channel.mention,
                message_url=result.message.jump_url if result.message is not None else "",
            ),
            ephemeral=True,
        )


async def setup(bot: NetworkRelayBot) -> None:
    await bot.add_cog(ServerCog(bot))
