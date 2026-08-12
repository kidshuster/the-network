from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

import discord

from bot.app.testing.catalog import (
    ALL_SCENARIOS_CHOICE,
    expand_scenarios_for_recipe,
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
        scenarios = expand_scenarios_for_recipe(name, scenario_name)
        scenario_label = (
            f"all ({len(scenarios)}: {', '.join(scenarios)})"
            if scenario_name == ALL_SCENARIOS_CHOICE and len(scenarios) > 1
            else scenarios[0] if scenario_name == ALL_SCENARIOS_CHOICE else scenario_name
        )
        return OpenEphemeralView(
            template_id="test_smoke_confirm",
            content=render_text(
                "test_smoke_confirm_prompt",
                recipe=name,
                scenario=scenario_label,
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
    scenarios = expand_scenarios_for_recipe(recipe_name, scenario)
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

    async def on_progress(phase: str, metrics: Any, *, current_scenario: str) -> None:
        nonlocal progress_message
        content = (
            f"Smoke `{run.run_id}` · `{recipe_name}` · `{current_scenario}`\n"
            f"phase `{phase}` · elapsed {metrics.duration_seconds:.1f}s\n"
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
        scenario_note = (
            f"scenarios ({len(scenarios)}): {', '.join(scenarios)}"
            if len(scenarios) > 1
            else f"scenario `{scenarios[0]}`"
        )
        await interaction.followup.send(
            f"Starting smoke run `{run.run_id}` · recipe `{recipe_name}` · {scenario_note}",
            ephemeral=True,
        )
        results: list[Any] = []
        for index, scenario_name in enumerate(scenarios, start=1):
            if run.cancel_event.is_set():
                break
            await interaction.followup.send(
                f"[{index}/{len(scenarios)}] Running `{recipe_name}` · `{scenario_name}`…",
                ephemeral=True,
            )

            async def _progress(phase: str, metrics: Any, *, _s: str = scenario_name) -> None:
                await on_progress(phase, metrics, current_scenario=_s)

            result = await run_smoke_recipe(
                recipe_name=recipe_name,
                scenario=scenario_name,
                backend="live",
                bot=bot,
                guild=guild,
                run_id=f"{run.run_id}-{scenario_name}",
                log_dir=log_dir,
                cancel_event=run.cancel_event,
                on_progress=_progress,
                max_rate_limit_wait_seconds=float(
                    settings.test_max_rate_limit_wait_seconds
                ),
            )
            results.append(result)
            status = "PASS" if result.success else "FAIL"
            line = (
                f"{status} `{scenario_name}` in {result.metrics.duration_seconds:.1f}s "
                f"(mutations={result.metrics.mutations}, "
                f"rest_reads={result.metrics.rest_reads})"
            )
            if result.error:
                line += f"\nError: {result.error}"
            await interaction.followup.send(line, ephemeral=True)
            if result.log_path is not None:
                note = await attach_log_file(interaction.followup.send, result.log_path)
                await interaction.followup.send(note, ephemeral=True)
            if not result.success:
                # Stop the matrix on first failure; remaining scenarios stay unrun.
                break

        passed = sum(1 for item in results if item.success)
        failed = sum(1 for item in results if not item.success)
        cancelled = run.cancel_event.is_set() and len(results) < len(scenarios)
        overall_success = (
            failed == 0 and not cancelled and len(results) == len(scenarios)
        )
        skipped = len(scenarios) - len(results)
        summary = (
            f"{'PASS' if overall_success else 'FAIL'} smoke suite `{run.run_id}` "
            f"`{recipe_name}` · {passed} passed · {failed} failed"
            + (f" · {skipped} skipped" if skipped else "")
        )
        await interaction.followup.send(summary, ephemeral=True)
        return {
            "success": overall_success,
            "run_id": run.run_id,
            "message": summary,
            "error": None if overall_success else summary,
        }
    finally:
        coordinator.end(run.run_id)
