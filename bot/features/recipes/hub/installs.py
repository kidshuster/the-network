from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.core.views import ViewRegistry
from bot.features.channels.layout.loader import load_layout
from bot.features.channels.layout.schema import ChannelInstallSpec
from bot.features.channels.resolve import resolve_hub_channel
from bot.features.channels.stickies.loader import sticky_spec
from bot.features.recipes.hub.result import GuildInitResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelInstallRef:
    resource_id: str
    install: ChannelInstallSpec


@dataclass
class InstallPassResult:
    success: bool = True
    notes: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    cleared_settings_keys: tuple[str, ...] = ()


def build_hub_install_plan() -> tuple[ChannelInstallRef, ...]:
    layout = load_layout().layout
    refs: list[ChannelInstallRef] = []
    for category in layout.categories.values():
        for resource_id, channel in category.channels.items():
            for install in channel.installs:
                refs.append(ChannelInstallRef(resource_id=resource_id, install=install))
    return tuple(refs)


def hub_sticky_settings_keys() -> tuple[str, ...]:
    keys: list[str] = []
    for ref in build_hub_install_plan():
        if ref.install.sticky is None:
            continue
        key = sticky_spec(ref.install.sticky).settings_key
        if key:
            keys.append(key)
    return tuple(dict.fromkeys(keys))


def _resolve_view(
    view_registry: ViewRegistry | None,
    view_key: str | None,
) -> discord.ui.View | None:
    if view_registry is None or view_key is None:
        return None
    if view_key == "join_network":
        register = getattr(view_registry, "register_join_network_view", None)
    elif view_key == "network_admin":
        register = getattr(view_registry, "register_network_admin_view", None)
    else:
        return None
    if register is None:
        return None
    view = register()
    return view if isinstance(view, discord.ui.View) else None


async def ensure_hub_installs(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    context: Any,
    bot: Any | None = None,
    view_registry: ViewRegistry | None = None,
    bound_ids: Mapping[str, int] | None = None,
) -> InstallPassResult:
    result = InstallPassResult()
    bound = dict(bound_ids or {})
    for ref in build_hub_install_plan():
        channel = _resolve_install_channel(guild, ref.resource_id, bound)
        try:
            notes = await _ensure_one_install(
                guild,
                bot_member,
                ref,
                channel=channel,
                context=context,
                bot=bot,
                view_registry=view_registry,
            )
            result.notes.extend(notes)
        except Exception as exc:
            logger.exception("Hub install failed", extra={"resource_id": ref.resource_id})
            result.failed_steps.append(f"{ref.resource_id}: {type(exc).__name__}: {exc}")
            # Keep success=True so recipe.run does not abort init; warnings collect in failed_steps.
    return result


def _resolve_install_channel(
    guild: discord.Guild,
    resource_id: str,
    bound_ids: Mapping[str, int],
) -> discord.TextChannel | None:
    discord_id = bound_ids.get(resource_id)
    if discord_id is not None:
        channel = guild.get_channel(discord_id)
        if isinstance(channel, discord.TextChannel):
            return channel
    return resolve_hub_channel(guild, resource_id)


async def _ensure_sticky_install(
    guild: discord.Guild,
    bot_member: discord.Member,
    ref: ChannelInstallRef,
    *,
    channel: discord.TextChannel,
    context: Any,
    view_registry: ViewRegistry | None,
) -> list[str]:
    sticky_id = ref.install.sticky
    assert sticky_id is not None
    view = _resolve_view(view_registry, ref.install.view)
    if sticky_id == "join-the-network":
        from bot.features.channels.stickies.join import sync_hub_join_sticky

        if view is None:
            return ["Skipped join sticky: view unavailable."]
        join_result = await sync_hub_join_sticky(
            guild,
            bot_member,
            channel,
            view,
            get_setting=context.store.settings.get,
            set_setting=context.store.settings.set,
            wipe_channel=True,
        )
        if join_result.message is not None:
            return [f"Join guide synced in {channel.mention}."]
        return []
    if sticky_id == "hub-rules":
        from bot.features.channels.stickies.rules import sync_rules_sticky

        rules_result = await sync_rules_sticky(
            guild,
            bot_member,
            get_setting=context.store.settings.get,
            set_setting=context.store.settings.set,
        )
        if rules_result.message is not None:
            return ["Hub rules sticky synced."]
        return []
    if sticky_id == "network-admin":
        from bot.features.channels.stickies.admin import sync_network_admin_sticky

        if view is None:
            return ["Skipped network admin sticky: view unavailable."]
        admin_result = await sync_network_admin_sticky(
            guild,
            bot_member,
            channel,
            context,
            view,
            get_setting=context.store.settings.get,
            set_setting=context.store.settings.set,
            wipe_channel=True,
        )
        if admin_result.message is not None:
            return [f"Network admin panel synced in {channel.mention}."]
        if admin_result.reason:
            return [f"Network admin sticky: {admin_result.reason}"]
        return []
    return [f"Unknown sticky install `{sticky_id}`."]


async def _ensure_one_install(
    guild: discord.Guild,
    bot_member: discord.Member,
    ref: ChannelInstallRef,
    *,
    channel: discord.TextChannel | None,
    context: Any,
    bot: Any | None,
    view_registry: ViewRegistry | None,
) -> list[str]:
    del bot
    install = ref.install

    if install.sticky is not None:
        if channel is None:
            return [
                f"Skipped sticky `{install.sticky}`: channel `{ref.resource_id}` missing."
            ]
        return await _ensure_sticky_install(
            guild,
            bot_member,
            ref,
            channel=channel,
            context=context,
            view_registry=view_registry,
        )

    if install.guide == "announcements":
        from bot.features.recipes.hub.announcements import sync_announcements_guide

        await sync_announcements_guide(guild, bot_member)
        return ["Announcements guide synced."]

    if install.sync == "changelog_releases":
        if channel is None:
            return ["Skipped changelog sync: channel missing."]
        from bot.features.recipes.hub.changelog import sync_changelog_releases
        from bot.features.recipes.hub.leaders import (
            CHANGELOG_CHANNEL_SETTINGS_KEY,
            LEADERS_CHANNEL_SETTINGS_KEY,
        )

        posted = await sync_changelog_releases(context, channel)
        await context.store.settings.set(CHANGELOG_CHANNEL_SETTINGS_KEY, str(channel.id))
        leaders = resolve_hub_channel(guild, "leaders_channel")
        if leaders is not None:
            await context.store.settings.set(LEADERS_CHANNEL_SETTINGS_KEY, str(leaders.id))
        if posted:
            return [f"Posted {posted} changelog release(s) to {channel.mention}."]
        return []

    if install.view is not None and install.sticky is None:
        return [f"View `{install.view}` requires a sticky install on `{ref.resource_id}`."]
    return []


@recipe("hub.ensure_installs")
async def ensure_installs_recipe(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    bot_member: discord.Member,
    bound_ids: Mapping[str, int] | None = None,
    view_registry: Any = None,
    result: GuildInitResult | None = None,
) -> InstallPassResult:

    registry = view_registry
    if registry is None:
        registry = recipe_context.bot.make_view_registry()
    pass_result = await ensure_hub_installs(
        guild,
        bot_member,
        context=recipe_context.core,
        bot=recipe_context.bot,
        view_registry=registry,
        bound_ids=bound_ids,
    )
    if result is not None:
        result.notes.extend(pass_result.notes)
        result.failed_steps.extend(pass_result.failed_steps)
    return pass_result


@recipe("hub.teardown_installs")
async def teardown_installs_recipe(
    recipe_context: RecipeContext,
    *,
    guild_id: int | None = None,
) -> InstallPassResult:
    del guild_id
    keys = hub_sticky_settings_keys()
    for key in keys:
        await recipe_context.core.store.settings.delete(key)
    return InstallPassResult(cleared_settings_keys=keys)
