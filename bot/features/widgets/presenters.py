from __future__ import annotations

from typing import Any

import discord

from bot.app.recipes import RecipeContext, recipe
from bot.app.templates import render_embed
from bot.errors import UserFacingError
from bot.features.hub.probe import ServerProbeReport
from bot.features.hub.result import GuildInitResult
from bot.features.recipes.hub.uninitialize import GuildUninitResult

_MAX_FIELD_CHARS = 1024
_MAX_FIELDS = 25


def _bullet_list(items: list[str], *, max_items: int = 25) -> str:
    lines: list[str] = []
    for item in items[:max_items]:
        line = f"• {item}"
        candidate = "\n".join((*lines, line))
        if len(candidate) > _MAX_FIELD_CHARS:
            omitted = len(items) - len(lines)
            if omitted > 0 and lines:
                lines.append(f"• … and {omitted} more")
            break
        lines.append(line)
    return "\n".join(lines)[:_MAX_FIELD_CHARS]


def _add_field(embed: discord.Embed, name: str, items: list[str]) -> None:
    if items and len(embed.fields) < _MAX_FIELDS:
        embed.add_field(name=name, value=_bullet_list(items), inline=False)


def server_init_embed(result: GuildInitResult) -> discord.Embed:
    if not result.success:
        raise UserFacingError(result.reason or "Server initialization failed.")
    from bot.app.layout.managed import hub_channel_name
    from bot.features.channels.resolve import HUB_CHANNEL_ADMIN

    embed = render_embed(
        "server_init_success",
        admin_channel=hub_channel_name(HUB_CHANNEL_ADMIN),
    )
    for name, items in (
        ("Categories created", result.created_categories),
        ("Channels created", result.created_channels),
        ("Channels moved", result.moved_channels),
        ("Roles", result.updated_roles),
        ("Notes", result.notes),
    ):
        _add_field(embed, name, items)
    if result.failed_steps:
        embed.colour = discord.Colour.gold()
        _add_field(embed, "Permission warnings", result.failed_steps)
    return embed


def server_rectification_embeds(result: GuildInitResult) -> list[discord.Embed]:
    if not result.success:
        return []
    groups = (
        ("Rectified", result.rectifications),
        ("Skipped", result.rectification_skipped),
        ("Rectification warnings", result.rectification_failures),
    )
    if not any(items for _, items in groups):
        embed = render_embed("server_init_rectification")
        embed.description = (
            "Existing client profiles and Leaders channels were checked. "
            "No registered clients needed permission rectification."
        )
        return [embed]
    embeds: list[discord.Embed] = []
    current = render_embed("server_init_rectification")
    embeds.append(current)
    for name, items in groups:
        for item in items:
            if len(current.fields) >= _MAX_FIELDS:
                current = render_embed("server_init_rectification")
                current.description = "Rectification report (continued)."
                embeds.append(current)
            _add_field(current, name, [item])
            if name == "Rectification warnings":
                current.colour = discord.Colour.gold()
    return embeds


@recipe("present.server.init")
async def present_server_init(
    recipe_context: RecipeContext,
    *,
    response: Any,
    value: object,
) -> None:
    del recipe_context
    if not isinstance(value, GuildInitResult):
        raise TypeError("server.init returned an invalid result")
    await response.send(embed=server_init_embed(value), ephemeral=True)
    for embed in server_rectification_embeds(value):
        await response.send(embed=embed, ephemeral=True)


@recipe("present.server.uninit")
async def present_server_uninit(
    recipe_context: RecipeContext,
    *,
    response: Any,
    value: object,
) -> None:
    del recipe_context
    if not isinstance(value, GuildUninitResult):
        raise TypeError("server.uninit returned an invalid result")
    if not value.success:
        raise UserFacingError(value.reason or "Server removal failed.")
    embed = render_embed("server_uninit_success")
    for name, items in (
        ("Categories deleted", value.deleted_categories),
        ("Channels deleted", value.deleted_channels),
        ("Roles deleted", value.deleted_roles),
        ("Preserved", value.preserved_channels),
        ("Notes", value.notes),
    ):
        _add_field(embed, name, items)
    await response.send(embed=embed, ephemeral=True)


def server_probe_embed(report: ServerProbeReport) -> discord.Embed:
    embed = render_embed("server_probe_report")
    passed = [f"**{check.name}**: {check.detail}" for check in report.passed_checks]
    failed = [f"**{check.name}**: {check.detail}" for check in report.failed_checks]
    if report.passed:
        embed.description = f"All {len(report.checks)} hub health check(s) passed."
        embed.colour = discord.Colour.green()
    else:
        embed.description = (
            f"{len(failed)} of {len(report.checks)} check(s) failed. "
            "Fix the issues below, then re-run `/server probe` or `/server init`."
        )
        embed.colour = discord.Colour.gold()
    _add_field(embed, "Passed", passed)
    _add_field(embed, "Failed", failed)
    return embed


@recipe("present.server.probe")
async def present_server_probe(
    recipe_context: RecipeContext,
    *,
    response: Any,
    value: object,
) -> None:
    del recipe_context
    if not isinstance(value, ServerProbeReport):
        raise TypeError("server.probe returned an invalid result")
    await response.send(embed=server_probe_embed(value), ephemeral=True)


@recipe("present.server.sync_join_guide")
async def present_join_guide(
    recipe_context: RecipeContext,
    *,
    response: Any,
    value: object,
) -> None:
    del recipe_context
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError("server.sync_join_guide returned an invalid result")
    result, channel = value
    if not result.success:
        raise UserFacingError(result.reason or "Join guide synchronization failed.")
    await response.send(
        embed=render_embed(
            "sync_join_guide_success",
            channel_mention=channel.mention,
            message_url=result.message.jump_url if result.message is not None else "",
        ),
        ephemeral=True,
    )
