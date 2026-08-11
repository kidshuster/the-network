from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import discord

from bot.app.discord.commands import register_recipe_commands
from bot.core.triggers import TriggerKind, TriggerSpec


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.tree = MagicMock()
    bot.trigger_catalog.list_by_kind.return_value = (
        TriggerSpec(
            id="server.init",
            kind=TriggerKind.SLASH,
            recipe="server.init",
            slash_group="server",
            slash_name="init",
            slash_description="Initialize server",
            default_permissions=("manage_guild",),
            presenter="present.server.init",
        ),
        TriggerSpec(
            id="server.uninit",
            kind=TriggerKind.SLASH,
            recipe="server.uninit",
            slash_group="server",
            slash_name="uninit",
            slash_description="Remove server layout",
            default_permissions=("manage_guild",),
            presenter="present.server.uninit",
        ),
    )
    bot.dispatch_trigger = AsyncMock(return_value=SimpleNamespace(success=True))
    return bot


def test_command_adapter_batches_trigger_metadata_into_group() -> None:
    bot = _bot()

    register_recipe_commands(bot)

    group = bot.tree.add_command.call_args.args[0]
    assert group.name == "server"
    assert {command.name for command in group.commands} == {"init", "uninit"}
    assert all(command.default_permissions.manage_guild for command in group.commands)


async def test_generated_command_runs_trigger_and_presenter(
    monkeypatch,
) -> None:
    bot = _bot()
    result = SimpleNamespace(success=True)
    bot.dispatch_trigger = AsyncMock(return_value=result)
    bot.recipe_registry.run = AsyncMock()
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

    bot.dispatch_trigger.assert_awaited_once_with("server.init", interaction=interaction)
    bot.recipe_registry.run.assert_awaited_once_with(
        "present.server.init",
        response=ANY,
        value=result,
    )


async def test_generated_command_enforces_declared_permissions() -> None:
    bot = _bot()
    bot.dispatch_trigger = AsyncMock()
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

    bot.dispatch_trigger.assert_not_awaited()
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Permission Required"
