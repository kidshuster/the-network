from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

import discord

from bot.app.testing.catalog import (
    requires_confirmation,
    validate_recipe_choice,
    validate_scenario_choice,
)
from bot.app.testing.coordinator import SmokeRunCoordinator
from bot.contracts.recipes import RecipeContext, recipe
from bot.contracts.widgets import OpenEphemeralView, recipe_handler
from bot.core.templates import render_text
from bot.errors import UserFacingError

logger = logging.getLogger(__name__)


def _smoke_api() -> Any:
    return importlib.import_module(".".join(("tests", "core", "smoke_api")))


def _run_logging() -> Any:
    return importlib.import_module(".".join(("tests", "core", "run_logging")))


def _coordinator(bot: Any) -> SmokeRunCoordinator:
    coordinator = getattr(bot, "smoke_run_coordinator", None)
    if coordinator is None:
        coordinator = SmokeRunCoordinator()
        bot.smoke_run_coordinator = coordinator
    return coordinator


def _require_test_guild(bot: Any, guild: discord.Guild | None) -> discord.Guild:
    settings = bot.settings
    if not settings.enable_test_commands:
        raise UserFacingError("Test commands are disabled.", code="test_commands_disabled")
    if guild is None or settings.test_guild_id is None or guild.id != settings.test_guild_id:
        raise UserFacingError(
            "This command can only be used in the configured test guild.",
            code="test_guild_required",
        )
    return guild


def _require_manage_guild_member(user: discord.abc.User) -> discord.Member:
    if not isinstance(user, discord.Member):
        raise UserFacingError("Guild membership is required.", code="member_required")
    permissions = user.guild_permissions
    if not permissions.manage_guild:
        raise UserFacingError(
            "You need **Manage Server** permission to run this command.",
            title="Permission Required",
            code="permission_required",
        )
    return user


@recipe("test.smoke.open")
async def open_smoke_test(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    recipe_name: str,
    scenario: str = "healthy",
) -> Any:
    bot = recipe_context.bot
    guild = _require_test_guild(bot, interaction.guild)
    member = _require_manage_guild_member(interaction.user)
    name = validate_recipe_choice(recipe_name)
    scenario_name = validate_scenario_choice(scenario)
    coordinator = _coordinator(bot)
    if coordinator.active_run is not None:
        active = coordinator.active_run
        raise UserFacingError(
            f"A smoke run is already active (`{active.run_id}`: {active.recipe_name}).",
            code="smoke_run_active",
        )
    if requires_confirmation(name):
        return OpenEphemeralView(
            template_id="test_smoke_confirm",
            content=render_text(
                "test_smoke_confirm_prompt",
                recipe=name,
                scenario=scenario_name,
            ),
            bindings={
                "confirm_button": recipe_handler(
                    "test.smoke.confirm",
                    recipe_name=name,
                    scenario=scenario_name,
                ),
                "cancel_button": recipe_handler("test.smoke.cancel"),
            },
        )
    await _execute_smoke(
        recipe_context,
        interaction=interaction,
        guild=guild,
        member=member,
        recipe_name=name,
        scenario=scenario_name,
    )
    return None


@recipe("test.smoke.confirm")
async def confirm_smoke_test(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    recipe_name: str,
    scenario: str = "healthy",
) -> Any:
    bot = recipe_context.bot
    guild = _require_test_guild(bot, interaction.guild)
    member = _require_manage_guild_member(interaction.user)
    await _execute_smoke(
        recipe_context,
        interaction=interaction,
        guild=guild,
        member=member,
        recipe_name=validate_recipe_choice(recipe_name),
        scenario=validate_scenario_choice(scenario),
    )
    return None


@recipe("test.smoke.cancel")
async def cancel_smoke_test(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
) -> str:
    del recipe_context, interaction
    return "Smoke test cancelled."


async def _execute_smoke(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
    guild: discord.Guild,
    member: discord.Member,
    recipe_name: str,
    scenario: str,
) -> dict[str, Any]:
    bot = recipe_context.bot
    settings = bot.settings
    log_dir = Path(settings.test_command_log_dir)
    coordinator = _coordinator(bot)
    pending_path = log_dir / "pending.log"
    run = await coordinator.begin(
        recipe_name=recipe_name,
        scenario=scenario,
        guild_id=guild.id,
        requester_id=member.id,
        log_path=pending_path,
    )
    if run is None:
        active = coordinator.active_run
        active_id = active.run_id if active is not None else "unknown"
        raise UserFacingError(
            f"A smoke run is already active (`{active_id}`).",
            code="smoke_run_active",
        )
    run_logging = _run_logging()
    run.log_path = run_logging.make_run_log_path(log_dir, recipe_name, run.run_id)
    run_smoke_recipe = _smoke_api().run_smoke_recipe
    attach_log_file = run_logging.attach_log_file

    progress_message: Any = None

    async def on_progress(phase: str, metrics: Any) -> None:
        nonlocal progress_message
        content = (
            f"Smoke `{run.run_id}` · `{recipe_name}` · phase `{phase}`\n"
            f"mutations={metrics.mutations} rest_reads={metrics.rest_reads} "
            f"wait={metrics.rate_limit_wait_seconds:.1f}s"
        )
        try:
            if progress_message is None:
                progress_message = await interaction.followup.send(
                    content, ephemeral=True
                )  # type: ignore[func-returns-value]
            else:
                await progress_message.edit(content=content)
        except discord.HTTPException:
            logger.debug("Could not update smoke progress message", exc_info=True)

    try:
        await interaction.followup.send(
            f"Starting smoke run `{run.run_id}` · recipe `{recipe_name}` · scenario `{scenario}`",
            ephemeral=True,
        )
        result = await run_smoke_recipe(
            recipe_name=recipe_name,
            scenario=scenario,
            backend="live",
            bot=bot,
            guild=guild,
            run_id=run.run_id,
            log_dir=log_dir,
            cancel_event=run.cancel_event,
            on_progress=on_progress,
            max_rate_limit_wait_seconds=float(settings.test_max_rate_limit_wait_seconds),
        )
        summary = (
            f"{'PASS' if result.success else 'FAIL'} smoke `{result.run_id}` "
            f"`{recipe_name}` in {result.metrics.duration_seconds:.1f}s\n"
            f"mutations={result.metrics.mutations} "
            f"rest_reads={result.metrics.rest_reads} "
            f"rate_limit_wait={result.metrics.rate_limit_wait_seconds:.1f}s"
        )
        if result.error:
            summary += f"\nError: {result.error}"
        await interaction.followup.send(summary, ephemeral=True)
        if result.log_path is not None:
            note = await attach_log_file(interaction.followup.send, result.log_path)
            await interaction.followup.send(note, ephemeral=True)
        return {
            "success": result.success,
            "run_id": result.run_id,
            "message": summary,
            "error": result.error,
        }
    finally:
        coordinator.end(run.run_id)
