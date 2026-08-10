from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from bot.constants import LEGACY_MODERATOR_ROLE_NAME
from bot.domain.client import Client
from bot.services.guild_init_result import GuildInitResult
from bot.services.guild_layout import (
    CATEGORY_NETWORK,
    CHANNEL_JOIN_REQUESTS,
    CHANNEL_LEADERS,
    CHANNEL_RULES,
    LEGACY_CHANNEL_LEADERS,
    resolve_category,
    resolve_human_moderator_role,
)
from bot.services.guild_permissions import (
    OverwriteMap,
    apply_overwrites_with_fallback,
    filter_configurable_overwrites,
    prepare_category_create_overwrites,
    sync_client_category_permissions,
)
from bot.services.step_runner import run_guild_step

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

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


async def _edit_overwrites(
    bot_member: discord.Member,
    target: discord.abc.GuildChannel,
    overwrites: OverwriteMap,
    *,
    result: GuildInitResult,
    step: str,
    sync_from_category: bool = False,
    **edit_kwargs: object,
) -> bool:
    reason = "The Network guild init"

    async def _edit() -> bool:
        await apply_overwrites_with_fallback(
            target,
            bot_member,
            overwrites,
            reason=reason,
            sync_from_category=sync_from_category,
            **edit_kwargs,
        )
        return True

    edited = await _run_init_step(result, step, _edit, fallback=False)
    is_channel = not isinstance(target, discord.CategoryChannel)
    if edited or not (sync_from_category and is_channel):
        return bool(edited)

    async def _sync_only() -> bool:
        await target.edit(  # type: ignore[attr-defined]
            sync_permissions=True,
            reason=reason,
            **edit_kwargs,
        )
        return True

    synced = await _run_init_step(
        result,
        f"{step} (inherit category)",
        _sync_only,
        fallback=False,
    )
    return bool(synced)


async def _ensure_category(
    guild: discord.Guild,
    bot_member: discord.Member,
    display_name: str,
    overwrites: OverwriteMap,
    *,
    result: GuildInitResult,
) -> discord.CategoryChannel | None:
    existing = resolve_category(guild, display_name)
    if existing is not None:
        await _edit_overwrites(
            bot_member,
            existing,
            overwrites,
            result=result,
            step=f"sync {display_name} category permissions",
        )
        return existing

    safe_overwrites = prepare_category_create_overwrites(
        bot_member,
        filter_configurable_overwrites(bot_member, overwrites),
    )

    async def _create() -> discord.CategoryChannel:
        return await guild.create_category(
            name=display_name,
            overwrites=safe_overwrites,
            reason="The Network guild init",
        )

    created = await _run_init_step(result, f"create {display_name} category", _create)
    if created is not None:
        result.created_categories.append(display_name)
    return created


async def _ensure_text_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    name: str,
    category: discord.CategoryChannel,
    overwrites: OverwriteMap,
    topic: str | None,
    result: GuildInitResult,
    sync_from_category: bool = False,
) -> discord.TextChannel | None:
    safe_overwrites = filter_configurable_overwrites(
        bot_member,
        overwrites,
        for_channel=True,
    )

    for channel in guild.text_channels:
        if channel.name.casefold() == name.casefold() and channel.category_id == category.id:
            await _edit_overwrites(
                bot_member,
                channel,
                overwrites,
                result=result,
                step=f"sync #{name} permissions",
                sync_from_category=sync_from_category,
                name=name,
                topic=topic,
            )
            return channel

    for channel in guild.text_channels:
        if channel.name.casefold() == name.casefold():
            moved = await _edit_overwrites(
                bot_member,
                channel,
                overwrites,
                result=result,
                step=f"move #{name} into {category.name}",
                sync_from_category=sync_from_category,
                category=category,
                name=name,
                topic=topic,
            )
            if moved:
                result.moved_channels.append(f"#{name} → {category.name}")
            return channel

    async def _create() -> discord.TextChannel:
        create_kwargs: dict[str, object] = {
            "name": name,
            "category": category,
            "reason": "The Network guild init",
        }
        if topic is not None:
            create_kwargs["topic"] = topic
        if sync_from_category:
            return await guild.create_text_channel(**create_kwargs)  # type: ignore[arg-type]
        create_kwargs["overwrites"] = safe_overwrites
        return await guild.create_text_channel(**create_kwargs)  # type: ignore[arg-type]

    created = await _run_init_step(result, f"create #{name}", _create)
    if created is not None:
        result.created_channels.append(f"#{name}")
    return created


async def _ensure_announcement_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    name: str,
    category: discord.CategoryChannel,
    overwrites: OverwriteMap,
    topic: str | None,
    result: GuildInitResult,
    sync_from_category: bool = False,
) -> discord.TextChannel | None:
    from bot.services.guild_permissions import create_text_channel_with_overwrites

    safe_overwrites = filter_configurable_overwrites(
        bot_member,
        overwrites,
        for_channel=True,
    )

    def _in_category(channel: discord.TextChannel) -> bool:
        return (
            channel.name.casefold() == name.casefold()
            and channel.category_id == category.id
        )

    deleted_legacy = False
    for channel in list(guild.text_channels):
        if not _in_category(channel):
            continue
        if channel.is_news():
            await _edit_overwrites(
                bot_member,
                channel,
                overwrites,
                result=result,
                step=f"sync #{name} permissions",
                sync_from_category=sync_from_category,
                name=name,
                topic=topic,
            )
            return channel

        async def _delete_wrong_type(ch: discord.TextChannel = channel) -> bool:
            await ch.delete(
                reason="The Network guild init: convert to announcement channel",
            )
            return True

        if await _run_init_step(
            result,
            f"recreate #{name} as announcement channel",
            _delete_wrong_type,
        ):
            deleted_legacy = True
            result.rectifications.append(f"Recreated #{name} as announcement channel")

    if deleted_legacy:
        await asyncio.sleep(1.0)

    for channel in list(guild.text_channels):
        if channel.name.casefold() != name.casefold():
            continue
        if _in_category(channel):
            continue
        if channel.is_news():
            moved = await _edit_overwrites(
                bot_member,
                channel,
                overwrites,
                result=result,
                step=f"move #{name} into {category.name}",
                sync_from_category=sync_from_category,
                category=category,
                name=name,
                topic=topic,
            )
            if moved:
                result.moved_channels.append(f"#{name} → {category.name}")
            return channel

        async def _delete_mismatch(ch: discord.TextChannel = channel) -> bool:
            await ch.delete(
                reason="The Network guild init: replace with announcement channel",
            )
            return True

        if await _run_init_step(
            result,
            f"remove non-announcement #{name}",
            _delete_mismatch,
        ):
            deleted_legacy = True

    if deleted_legacy:
        await asyncio.sleep(1.0)

    for channel in guild.text_channels:
        if _in_category(channel) and channel.is_news():
            await _edit_overwrites(
                bot_member,
                channel,
                overwrites,
                result=result,
                step=f"sync #{name} permissions",
                sync_from_category=sync_from_category,
                name=name,
                topic=topic,
            )
            return channel

    async def _create() -> discord.TextChannel:
        if sync_from_category:
            create_kwargs: dict[str, object] = {
                "name": name,
                "category": category,
                "news": True,
                "reason": "The Network guild init",
            }
            if topic is not None:
                create_kwargs["topic"] = topic
            return await guild.create_text_channel(**create_kwargs)  # type: ignore[arg-type]
        return await create_text_channel_with_overwrites(
            guild,
            bot_member,
            name=name,
            category=category,
            overwrites=safe_overwrites,
            topic=topic,
            news=True,
            reason="The Network guild init",
        )

    created = await _run_init_step(
        result,
        f"create #{name} announcement channel",
        _create,
    )
    if created is not None:
        result.created_channels.append(f"#{name}")
        if not created.is_news():
            result.rectification_failures.append(
                f"#{name} was created but is not an announcement channel."
            )
            return None
        return created

    legacy = next(
        (
            channel
            for channel in guild.text_channels
            if _in_category(channel) and not channel.is_news()
        ),
        None,
    )
    if legacy is not None:
        result.rectification_failures.append(
            f"Could not convert {legacy.mention} to an announcement channel "
            "(delete/recreate failed — check bot **Manage Channels**)."
        )
    return None


async def _ensure_human_moderator_role(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    result: GuildInitResult,
) -> discord.Role | None:
    role = resolve_human_moderator_role(guild)
    if role is not None:
        if bot_member.top_role.position > role.position:
            needs_update = (
                role.permissions != _MODERATOR_GUILD_PERMISSIONS
                or not role.mentionable
            )

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
                f"**#{CHANNEL_JOIN_REQUESTS}** will not ping moderators until "
                f"**{role.name}** is set to mentionable."
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


async def _move_rules_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
    network_category: discord.CategoryChannel,
    overwrites: OverwriteMap,
    *,
    result: GuildInitResult,
) -> None:
    rules = guild.rules_channel
    if isinstance(rules, discord.TextChannel):
        edit_kwargs: dict[str, object] = {}
        if rules.category_id != network_category.id or rules.name != CHANNEL_RULES:
            edit_kwargs["category"] = network_category
            edit_kwargs["name"] = CHANNEL_RULES
        synced = await _edit_overwrites(
            bot_member,
            rules,
            overwrites,
            result=result,
            step=f"sync rules channel {rules.mention}",
            sync_from_category=rules.category_id == network_category.id,
            **edit_kwargs,
        )
        if synced and edit_kwargs:
            result.moved_channels.append(f"{rules.mention} → {CATEGORY_NETWORK}/{CHANNEL_RULES}")
        return

    await _ensure_text_channel(
        guild,
        bot_member,
        name=CHANNEL_RULES,
        category=network_category,
        overwrites=overwrites,
        topic="Hub relay rules for The Network",
        result=result,
    )
    result.notes.append(
        "Set this channel as the Community rules channel under Server Settings if needed."
    )


async def _find_moderator_only_channel(guild: discord.Guild) -> discord.TextChannel | None:
    for channel in guild.text_channels:
        lowered = channel.name.casefold()
        if lowered in {"moderator-only", "mod-only", "staff-only"}:
            return channel
    return None


async def _sync_client_categories(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    clients: list[Client],
    *,
    result: GuildInitResult,
) -> None:
    clients_by_category = {
        client.category_id: client
        for client in clients
        if client.guild_id == guild.id
    }
    if not clients_by_category:
        return

    for category in guild.categories:
        client = clients_by_category.get(category.id)
        if client is None:
            continue
        client_role = guild.get_role(client.client_role_id)
        if client_role is None:
            result.notes.append(
                f"Skipped category {category.name}: client role missing"
            )
            continue

        async def _sync(
            cat: discord.CategoryChannel = category,
            role: discord.Role = client_role,
        ) -> bool:
            await sync_client_category_permissions(
                cat,
                bot_member,
                role,
                access_role,
                human_moderator_role,
                reason="The Network server init",
            )
            return True

        if await _run_init_step(result, f"sync client category {category.name}", _sync):
            result.rectifications.append(
                f"**{client.server_name}**: rectified category permissions."
            )


async def _reorder_moderation_channels(
    moderation: discord.CategoryChannel,
    *,
    result: GuildInitResult,
) -> None:
    order = ["moderator-only", "network-announcements", "join-requests", "commands"]
    channels = [
        ch for ch in moderation.channels if isinstance(ch, discord.TextChannel)
    ]
    by_name = {ch.name.casefold(): ch for ch in channels}
    for index, name in enumerate(order):
        channel = by_name.get(name)
        if channel is None:
            continue

        async def _move(ch: discord.TextChannel = channel, pos: int = index) -> None:
            await ch.edit(position=pos, reason="The Network server init")

        await _run_init_step(result, f"order #{name}", _move)


async def _reorder_guild_categories(
    moderation: discord.CategoryChannel,
    network_category: discord.CategoryChannel,
    *,
    leaders_category: discord.CategoryChannel | None = None,
    client_categories: list[discord.CategoryChannel] | None = None,
    result: GuildInitResult,
) -> None:
    """Hub order: Moderation, The Network, Leaders — then client categories."""
    ordered_hub = [moderation, network_category]
    if leaders_category is not None:
        ordered_hub.append(leaders_category)

    for index, category in enumerate(ordered_hub):

        async def _move(
            cat: discord.CategoryChannel = category,
            pos: int = index,
        ) -> None:
            await cat.edit(position=pos, reason="The Network server init")

        await _run_init_step(
            result,
            f"order hub category {category.name}",
            _move,
        )

    if not client_categories:
        return

    start = len(ordered_hub)
    for offset, category in enumerate(client_categories):
        pos = start + offset

        async def _move_client(
            cat: discord.CategoryChannel = category,
            position: int = pos,
        ) -> None:
            await cat.edit(position=position, reason="The Network server init")

        await _run_init_step(
            result,
            f"order client category {category.name}",
            _move_client,
        )


async def _reorder_hub_categories(
    moderation: discord.CategoryChannel,
    network_category: discord.CategoryChannel,
    *,
    result: GuildInitResult,
) -> None:
    await _reorder_guild_categories(
        moderation,
        network_category,
        result=result,
    )


async def _sync_hub_public_channels(
    guild: discord.Guild,
    bot_member: discord.Member,
    network_category: discord.CategoryChannel,
    overwrites: OverwriteMap,
    *,
    result: GuildInitResult,
) -> None:
    rules_channel_id = (
        guild.rules_channel.id
        if isinstance(guild.rules_channel, discord.TextChannel)
        else None
    )
    for channel in network_category.channels:
        if not isinstance(channel, discord.TextChannel):
            continue
        if rules_channel_id is not None and channel.id == rules_channel_id:
            continue
        if channel.name.casefold() in {
            CHANNEL_LEADERS.casefold(),
            LEGACY_CHANNEL_LEADERS.casefold(),
        }:
            continue
        if await _edit_overwrites(
            bot_member,
            channel,
            overwrites,
            result=result,
            step=f"sync hub channel #{channel.name}",
            sync_from_category=True,
        ):
            result.notes.append(f"Synced hub permissions on #{channel.name}")


async def _sync_hub_notification_defaults(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    result: GuildInitResult,
    step: str,
) -> None:
    from bot.services.guild_notifications import sync_guild_notification_policy

    async def _run() -> None:
        await sync_guild_notification_policy(
            guild,
            bot_member,
            reason="The Network guild init",
            result=result,
        )

    await _run_init_step(result, step, _run)


