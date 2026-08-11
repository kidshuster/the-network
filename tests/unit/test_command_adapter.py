from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from bot.adapters.discord.commands import register_recipe_commands
from bot.widgets.recipes.metadata import CommandSpec, RecipeSpec


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.tree = MagicMock()
    bot.recipe_registry.command_specs.return_value = (
        RecipeSpec(
            "server.init",
            command=CommandSpec(
                "server",
                "init",
                "Initialize server",
                default_permissions=("manage_guild",),
                presenter="server.init",
            ),
        ),
        RecipeSpec(
            "server.uninit",
            command=CommandSpec(
                "server",
                "uninit",
                "Remove server layout",
                default_permissions=("manage_guild",),
                presenter="server.uninit",
            ),
        ),
    )
    return bot


def test_command_adapter_batches_recipe_metadata_into_group() -> None:
    bot = _bot()

    register_recipe_commands(bot)

    group = bot.tree.add_command.call_args.args[0]
    assert group.name == "server"
    assert {command.name for command in group.commands} == {"init", "uninit"}
    assert all(command.default_permissions.manage_guild for command in group.commands)


async def test_generated_command_runs_recipe_and_presenter(
    monkeypatch,
) -> None:
    bot = _bot()
    result = SimpleNamespace(success=True)
    bot.recipe_registry.run = AsyncMock(return_value=result)
    presented = AsyncMock()
    monkeypatch.setattr("bot.adapters.discord.commands.present_result", presented)
    register_recipe_commands(bot)
    group = bot.tree.add_command.call_args.args[0]
    command = group.get_command("init")
    assert command is not None

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 100
    interaction.user.guild_permissions.manage_guild = True
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    await command.callback(interaction)

    bot.recipe_registry.run.assert_awaited_once_with("server.init", interaction=interaction)
    presented.assert_awaited_once()


async def test_generated_command_enforces_declared_permissions() -> None:
    bot = _bot()
    bot.recipe_registry.run = AsyncMock()
    register_recipe_commands(bot)
    command = bot.tree.add_command.call_args.args[0].get_command("init")
    assert command is not None

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 100
    interaction.guild.public_updates_channel = None
    interaction.guild.text_channels = []
    interaction.user.guild_permissions.manage_guild = False
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    await command.callback(interaction)

    bot.recipe_registry.run.assert_not_awaited()
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Permission Required"
