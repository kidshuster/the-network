from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import discord

from bot.core.hub.result import GuildInitResult
from bot.errors import UserFacingError
from bot.presentation import render_embed
from bot.recipes.hub.uninitialize import GuildUninitResult

Presenter = Callable[[Any, object], Awaitable[None]]
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
    embed = render_embed("server_init_success")
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


async def _present_server_init(response: Any, value: object) -> None:
    if not isinstance(value, GuildInitResult):
        raise TypeError("server.init returned an invalid result")
    await response.send(embed=server_init_embed(value), ephemeral=True)
    for embed in server_rectification_embeds(value):
        await response.send(embed=embed, ephemeral=True)


async def _present_server_uninit(response: Any, value: object) -> None:
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


async def _present_join_guide(response: Any, value: object) -> None:
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


_PRESENTERS: dict[str, Presenter] = {
    "server.init": _present_server_init,
    "server.uninit": _present_server_uninit,
    "server.sync_join_guide": _present_join_guide,
}


async def present_result(presenter: str | None, response: Any, value: object) -> None:
    if presenter is None:
        await response.send(content="Operation completed.", ephemeral=True)
        return
    try:
        handler = _PRESENTERS[presenter]
    except KeyError as exc:
        raise RuntimeError(f"Unknown result presenter {presenter!r}") from exc
    await handler(response, value)
