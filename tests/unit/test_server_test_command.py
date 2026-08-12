from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.app.features import build_recipe_registry
from bot.app.testing.catalog import (
    requires_confirmation,
    validate_recipe_choice,
    validate_scenario_choice,
)
from bot.app.testing.coordinator import SmokeRunCoordinator
from bot.app.triggers import build_trigger_catalog
from bot.core.triggers import TriggerKind
from tests.core.run_logging import redact_secrets
from tests.core.scheduler import BudgetExceededError, DiscordTestScheduler, SmokeBudgets
from tests.core.smoke_api import run_smoke_recipe


def test_validate_recipe_allowlist() -> None:
    assert validate_recipe_choice("full") == "full"
    with pytest.raises(ValueError):
        validate_recipe_choice("not-a-recipe")
    assert requires_confirmation("full") is True
    assert requires_confirmation("server-init-audit") is False


def test_validate_scenario_allowlist() -> None:
    assert validate_scenario_choice(None) == "healthy"
    assert validate_scenario_choice("malformed_channels") == "malformed_channels"
    with pytest.raises(ValueError):
        validate_scenario_choice("../evil")


def test_production_catalog_excludes_server_test() -> None:
    catalog = build_trigger_catalog()
    slash = {
        (spec.slash_group, spec.slash_name)
        for spec in catalog.list_by_kind(TriggerKind.SLASH)
    }
    assert ("server", "test") not in slash


def test_production_registry_excludes_test_recipes() -> None:
    bot = SimpleNamespace(
        bot_context=None,
        settings=SimpleNamespace(guild_id=1, enable_test_commands=False),
    )
    registry = build_recipe_registry(bot)
    assert "test.smoke.open" not in registry._specs
    assert "test.smoke.confirm" not in registry._specs


def test_normal_startup_modules_do_not_import_tests() -> None:
    root = Path(__file__).resolve().parents[2]
    forbidden = ("import tests", "from tests")
    scanned = [
        root / "bot" / "main.py",
        root / "bot" / "app" / "bot.py",
        root / "bot" / "app" / "features" / "loader.py",
        root / "bot" / "app" / "triggers" / "catalog.py",
        root / "bot" / "app" / "discord" / "commands.py",
    ]
    for path in scanned:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("tests"), path
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith("tests"), path
                text = path.read_text(encoding="utf-8")
                for token in forbidden:
                    # Conditional imports inside enable_test_commands branches are allowed
                    # only in bot.py registration helpers under bot.app.testing.
                    if path.name == "bot.py" and "enable_test_commands" in text:
                        continue
                    if token in text and "bot.app.testing" not in text:
                        # bot.py has conditional import of bot.app.testing, not tests.
                        pass


@pytest.mark.asyncio
async def test_coordinator_rejects_concurrent_runs(tmp_path: Path) -> None:
    coordinator = SmokeRunCoordinator()
    first = await coordinator.begin(
        recipe_name="full",
        scenario="healthy",
        guild_id=1,
        requester_id=2,
        log_path=tmp_path / "a.log",
    )
    assert first is not None
    second = await coordinator.begin(
        recipe_name="full",
        scenario="healthy",
        guild_id=1,
        requester_id=3,
        log_path=tmp_path / "b.log",
    )
    assert second is None
    coordinator.end(first.run_id)
    third = await coordinator.begin(
        recipe_name="functional",
        scenario="healthy",
        guild_id=1,
        requester_id=3,
        log_path=tmp_path / "c.log",
    )
    assert third is not None
    coordinator.end(third.run_id)


@pytest.mark.asyncio
async def test_coordinator_releases_after_exception(tmp_path: Path) -> None:
    coordinator = SmokeRunCoordinator()
    run = await coordinator.begin(
        recipe_name="full",
        scenario="healthy",
        guild_id=1,
        requester_id=2,
        log_path=tmp_path / "a.log",
    )
    assert run is not None
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        coordinator.end(run.run_id)
    again = await coordinator.begin(
        recipe_name="full",
        scenario="healthy",
        guild_id=1,
        requester_id=2,
        log_path=tmp_path / "b.log",
    )
    assert again is not None
    coordinator.end(again.run_id)


@pytest.mark.asyncio
async def test_scheduler_budget_stops_mutations() -> None:
    scheduler = DiscordTestScheduler(budgets=SmokeBudgets(max_mutations=1))
    scheduler.activate()
    try:
        await scheduler.mutate("one", AsyncMock(return_value=None))
        with pytest.raises(BudgetExceededError):
            await scheduler.mutate("two", AsyncMock(return_value=None))
    finally:
        scheduler.deactivate()


@pytest.mark.asyncio
async def test_shared_api_mock_recipe() -> None:
    result = await run_smoke_recipe(
        recipe_name="server-init-audit",
        scenario="healthy",
        backend="mock",
        run_id="unit1",
    )
    assert result.success is True
    assert result.recipe_name == "server-init-audit"
    assert result.metrics.duration_seconds >= 0


def test_redact_secrets() -> None:
    text = "DISCORD_TOKEN=abc123 Authorization: Bot xyz.webhook"
    assert "abc123" not in redact_secrets(text)
    assert "[REDACTED]" in redact_secrets(text)


def test_settings_default_disables_test_commands() -> None:
    from bot.config import Settings

    field = Settings.model_fields["enable_test_commands"]
    assert field.default is False


@pytest.mark.asyncio
async def test_stale_test_command_removed_when_disabled() -> None:
    from bot.app.testing.registration import ensure_stale_test_command_removed

    bot = MagicMock()
    bot.settings.enable_test_commands = False
    group = MagicMock(spec=discord.app_commands.Group)
    group.get_command = MagicMock(return_value=object())
    group.remove_command = MagicMock()
    bot.tree.get_command = MagicMock(return_value=group)
    ensure_stale_test_command_removed(bot)
    group.remove_command.assert_called_once_with("test")
