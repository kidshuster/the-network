from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord

from bot.app.layout.managed import hub_channel_name
from bot.constants import LEGACY_MODERATOR_ROLE_NAME
from bot.core.discord.step_runner import run_guild_step
from bot.features.channels.resolve import (
    HUB_CHANNEL_JOIN_REQUESTS,
    resolve_human_moderator_role,
)
from bot.features.recipes.hub.result import GuildInitResult

_MODERATOR_GUILD_PERMISSIONS = discord.Permissions(
    view_channel=True,
    send_messages=True,
    embed_links=True,
    attach_files=True,
    read_message_history=True,
    manage_messages=True,
    manage_channels=True,
    manage_roles=True,
    manage_webhooks=True,
    mention_everyone=False,
)


async def _run_init_step[T](
    result: GuildInitResult,
    step: str,
    action: Callable[[], Awaitable[T]],
    *,
    fallback: T | None = None,
) -> T | None:
    return await run_guild_step(result, step, action, fallback=fallback)


async def _ensure_human_moderator_role(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    result: GuildInitResult,
) -> discord.Role | None:
    role = resolve_human_moderator_role(guild)
    if role is not None:
        if bot_member.top_role.position > role.position:
            needs_update = role.permissions != _MODERATOR_GUILD_PERMISSIONS or not role.mentionable

            if needs_update:

                async def _update() -> discord.Role:
                    await role.edit(
                        permissions=_MODERATOR_GUILD_PERMISSIONS,
                        mentionable=True,
                        reason="The Network guild init",
                    )
                    return role

                updated = await _run_init_step(
                    result, f"update {role.name} role permissions", _update
                )
                if updated is not None:
                    result.updated_roles.append(f"Updated {role.name}")
        elif not role.mentionable:
            result.notes.append(
                f"**{role.name}** is not mentionable and the bot cannot edit that role "
                "(role is above the bot). Join requests in "
                f"**#{hub_channel_name(HUB_CHANNEL_JOIN_REQUESTS)}** will not ping "
                f"moderators until **{role.name}** is set to mentionable."
            )
        return role

    async def _create() -> discord.Role:
        return await guild.create_role(
            name=LEGACY_MODERATOR_ROLE_NAME,
            permissions=_MODERATOR_GUILD_PERMISSIONS,
            mentionable=True,
            hoist=True,
            reason="The Network guild init",
        )

    created = await _run_init_step(result, "create Moderator role", _create)
    if created is not None:
        result.updated_roles.append(f"Created {LEGACY_MODERATOR_ROLE_NAME}")
    return created


async def _sync_hub_notification_defaults(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    result: GuildInitResult,
    step: str,
) -> None:
    from bot.features.recipes.hub.notifications import sync_guild_notification_policy

    async def _run() -> None:
        await sync_guild_notification_policy(
            guild,
            bot_member,
            reason="The Network guild init",
            result=result,
        )

    await _run_init_step(result, step, _run)
