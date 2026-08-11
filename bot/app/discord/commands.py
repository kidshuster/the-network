from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

from bot.app.discord.errors import respond_to_error
from bot.app.discord.responses import defer_ephemeral
from bot.core.triggers import TriggerKind, TriggerSpec
from bot.errors import UserFacingError

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot


def _callback(bot: NetworkRelayBot, spec: TriggerSpec) -> Callable[..., Any]:
    async def invoke(interaction: discord.Interaction) -> None:
        response = await defer_ephemeral(interaction)
        try:
            guild = interaction.guild
            if guild is None or guild.id != bot.settings.guild_id:
                raise UserFacingError("This command can only be used in the configured hub guild.")
            member = interaction.user
            permissions = getattr(member, "guild_permissions", None)
            missing = [
                permission
                for permission in spec.default_permissions
                if permissions is None or not getattr(permissions, permission, False)
            ]
            if missing:
                raise UserFacingError(
                    "You need **Manage Server** permission to run this command.",
                    title="Permission Required",
                    code="permission_required",
                )
            value = await bot.dispatch_trigger(spec.id, interaction=interaction)
            if spec.presenter is None:
                await response.send(content="Operation completed.", ephemeral=True)
            else:
                await bot.recipe_registry.run(
                    spec.presenter,
                    response=response,
                    value=value,
                )
        except Exception as error:
            await respond_to_error(bot, interaction, response, error, operation=spec.id)

    invoke.__name__ = spec.id.replace(".", "_")
    return invoke


def register_recipe_commands(bot: NetworkRelayBot) -> None:
    groups: dict[str, app_commands.Group] = {}
    for spec in bot.trigger_catalog.list_by_kind(TriggerKind.SLASH):
        assert spec.slash_group is not None
        assert spec.slash_name is not None
        assert spec.slash_description is not None
        group = groups.get(spec.slash_group)
        if group is None:
            group = app_commands.Group(
                name=spec.slash_group,
                description=spec.slash_group_description,
                guild_only=True,
            )
            groups[spec.slash_group] = group
        callback = _callback(bot, spec)
        if spec.default_permissions:
            callback = app_commands.default_permissions(
                **{permission: True for permission in spec.default_permissions}
            )(callback)
        group.add_command(
            app_commands.Command(
                name=spec.slash_name,
                description=spec.slash_description,
                callback=callback,
            )
        )
    for group in groups.values():
        bot.tree.add_command(group)
