from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

from bot.app.discord.responses import defer_response
from bot.app.testing.catalog import allowed_recipe_names, allowed_scenario_names
from bot.contracts.widgets import OpenEphemeralView
from bot.errors import UserFacingError

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot


async def _invoke_server_test(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    recipe: str,
    scenario: str,
) -> None:
    response = await defer_response(interaction, ephemeral=True)
    try:
        value = await bot.recipe_registry.run(
            "test.smoke.open",
            interaction=interaction,
            recipe_name=recipe,
            scenario=scenario,
        )
        if value is None:
            return
        if isinstance(value, OpenEphemeralView):
            from bot.app.widgets.dispatch import _open_ephemeral_view

            await _open_ephemeral_view(bot, interaction, value)
            return
        if isinstance(value, dict):
            await response.send(content=str(value.get("message") or "Smoke finished."))
            return
        await response.send(content=str(value))
    except Exception as error:
        from bot.app.discord.errors import respond_to_error

        await respond_to_error(bot, interaction, response, error, operation="server.test")


def register_test_commands(bot: NetworkRelayBot) -> None:
    """Register `/server test` onto the existing guild command tree."""
    from bot.app.recipes.registry import collect_recipes
    from bot.app.testing import recipes as test_recipes
    from bot.app.testing.coordinator import SmokeRunCoordinator

    bot.recipe_registry.register_many(collect_recipes(test_recipes))
    if getattr(bot, "smoke_run_coordinator", None) is None:
        bot.smoke_run_coordinator = SmokeRunCoordinator()

    recipe_choices = [
        app_commands.Choice(name=name, value=name) for name in allowed_recipe_names()
    ]
    scenario_choices = [
        app_commands.Choice(name=name, value=name) for name in allowed_scenario_names()
    ]

    async def server_test(
        interaction: discord.Interaction,
        recipe: str,
        scenario: str = "healthy",
    ) -> None:
        if not bot.settings.enable_test_commands:
            raise UserFacingError("Test commands are disabled.", code="test_commands_disabled")
        await _invoke_server_test(bot, interaction, recipe, scenario)

    server_test = app_commands.choices(recipe=recipe_choices)(server_test)
    server_test = app_commands.choices(scenario=scenario_choices)(server_test)
    server_test = app_commands.default_permissions(manage_guild=True)(server_test)
    command: Any = app_commands.Command(
        name="test",
        description="Run an in-process smoke recipe (test mode only)",
        callback=server_test,
    )

    server_group = bot.tree.get_command("server")
    if server_group is None:
        server_group = app_commands.Group(
            name="server",
            description="Initialize and maintain the Discord hub server",
            guild_only=True,
        )
        bot.tree.add_command(server_group)
    if not isinstance(server_group, app_commands.Group):
        raise RuntimeError("Expected /server command group")
    if server_group.get_command("test") is not None:
        server_group.remove_command("test")
    server_group.add_command(command)


def ensure_stale_test_command_removed(bot: NetworkRelayBot) -> None:
    """Production path: drop a leftover /server test command before sync."""
    if bot.settings.enable_test_commands:
        return
    server_group = bot.tree.get_command("server")
    if isinstance(server_group, app_commands.Group) and server_group.get_command("test"):
        server_group.remove_command("test")
