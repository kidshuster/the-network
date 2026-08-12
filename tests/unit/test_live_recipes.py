from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tests.core.mock_backend import (
    MockClient,
    MockContext,
    MockDiscordState,
    load_mock_context,
)
from tests.core.probes import PROBES, ProbeOutcome
from tests.core.recipes import Recipe, RecipeRunner, RecipeStep, load_recipes
from tests.core.scheduler import DiscordTestScheduler, SmokeMetrics


def test_shipped_recipes_only_reference_registered_probes_and_recipes() -> None:
    recipes = load_recipes()
    assert {
        "audit",
        "clean",
        "functional",
        "full",
        "server-init-audit",
        "server-init-rectification",
        "server-init-stress",
        "stress",
    } <= recipes.keys()
    for recipe in recipes.values():
        for step in (*recipe.steps, *recipe.finally_steps):
            if step.probe is not None:
                assert step.probe in PROBES
            if step.recipe is not None:
                assert step.recipe in recipes


def test_recipe_loader_rejects_ambiguous_step(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text(
        "name: bad\nsteps:\n  - probe: hub.layout\n    recipe: audit\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly one"):
        load_recipes(tmp_path)


@pytest.mark.asyncio
async def test_runner_composes_recipes_and_runs_finally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_probe(_context: Any) -> ProbeOutcome:
        calls.append("probe")
        return ProbeOutcome("probe", "ok")

    async def fake_mock_probe(
        _name: str,
        context: MockContext,
        *,
        pause_after: bool = False,
    ) -> ProbeOutcome:
        _ = pause_after
        return await fake_probe(context)

    monkeypatch.setattr("tests.core.recipes.run_mock_probe", fake_mock_probe)
    monkeypatch.setattr(
        "tests.core.recipes.assert_protected_clients_unchanged",
        _noop_guard,
    )
    recipes = {
        "child": Recipe(
            "child", "", (RecipeStep(probe="one", protect_clients=False),)
        ),
        "parent": Recipe(
            "parent",
            "",
            (RecipeStep(recipe="child"),),
            (RecipeStep(probe="cleanup", protect_clients=False),),
        ),
    }
    runner = RecipeRunner(
        MockContext(MockDiscordState()), recipes, backend="mock"
    )
    await runner.run("parent")
    assert calls == ["probe", "probe"]


@pytest.mark.asyncio
async def test_runner_rejects_recipe_cycles() -> None:
    recipes = {
        "a": Recipe("a", "", (RecipeStep(recipe="b"),)),
        "b": Recipe("b", "", (RecipeStep(recipe="a"),)),
    }
    runner = RecipeRunner(
        MockContext(MockDiscordState()), recipes, backend="mock"
    )
    with pytest.raises(ValueError, match="a -> b -> a"):
        await runner.run("a")


async def _noop_guard(*_args: Any, **_kwargs: Any) -> None:
    return None


@pytest.mark.asyncio
async def test_full_mock_recipe_preserves_real_clients_and_cleans_smoke_state() -> None:
    context = load_mock_context("healthy")
    await RecipeRunner(context, load_recipes(), backend="mock").run("full")
    context.state.assert_protected()
    assert not context.state.artifacts
    assert all(not client.smoke for client in context.state.clients.values())
    assert "hub.rebuild" not in context.state.operations
    assert "relay.setup_welcome" in context.state.operations
    assert "hub.leaders_drift" in context.state.operations


@pytest.mark.asyncio
async def test_mock_clean_recipe_removes_smoke_clients() -> None:
    context = load_mock_context("healthy")
    context.state.clients["Smoke Accept leftover"] = MockClient(
        "Smoke Accept leftover", smoke=True
    )
    context.state.artifacts.add("leftover-role")
    await RecipeRunner(context, load_recipes(), backend="mock").run("clean")
    assert all(not client.smoke for client in context.state.clients.values())
    assert not context.state.artifacts
    context.state.assert_protected()


@pytest.mark.asyncio
async def test_mock_functional_recipe_rectifies_stale_permissions() -> None:
    context = load_mock_context("stale_permissions")
    assert not context.state.leaders_access
    await RecipeRunner(context, load_recipes(), backend="mock").run("functional")
    assert context.state.leaders_access


@pytest.mark.asyncio
async def test_mock_audit_exposes_missing_layout() -> None:
    context = load_mock_context("missing_layout")
    with pytest.raises(RuntimeError, match="admin channel is missing"):
        await RecipeRunner(context, load_recipes(), backend="mock").run("audit")


@pytest.mark.asyncio
async def test_server_init_stress_rectifies_malformed_live_server() -> None:
    context = load_mock_context("malformed_channels")
    await RecipeRunner(context, load_recipes(), backend="mock").run(
        "server-init-stress"
    )
    state = context.state
    assert state.layout_present
    assert state.leaders_access
    assert not state.missing_channels
    assert not state.misplaced_channels
    assert not state.wrong_channel_types
    assert not state.stale_permission_targets
    assert not state.stale_roles
    assert not state.duplicate_channels
    state.assert_protected()


@pytest.mark.asyncio
async def test_server_init_stress_reports_unrecoverable_visibility_blocker() -> None:
    context = load_mock_context("hard_blocker")
    with pytest.raises(RuntimeError, match="community channels hidden from bot"):
        await RecipeRunner(context, load_recipes(), backend="mock").run(
            "server-init-stress"
        )
    context.state.assert_protected()


@pytest.mark.asyncio
async def test_runner_emits_start_progress_before_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phases: list[str] = []
    probe_started = asyncio.Event()

    async def slow_mock_probe(
        name: str,
        context: MockContext,
        *,
        pause_after: bool = False,
    ) -> ProbeOutcome:
        _ = pause_after
        probe_started.set()
        assert phases[0] == f"start:{name}"
        context.state.operations.append(name)
        return ProbeOutcome(name, "ok")

    monkeypatch.setattr("tests.core.recipes.run_mock_probe", slow_mock_probe)
    monkeypatch.setattr(
        "tests.core.recipes.assert_protected_clients_unchanged",
        _noop_guard,
    )

    async def on_progress(phase: str, metrics: SmokeMetrics) -> None:
        _ = metrics
        phases.append(phase)

    recipes = {
        "one": Recipe("one", "", (RecipeStep(probe="hub.layout", protect_clients=False),))
    }
    scheduler = DiscordTestScheduler(phase_delay_seconds=0)
    await RecipeRunner(
        MockContext(MockDiscordState()),
        recipes,
        backend="mock",
        scheduler=scheduler,
        on_progress=on_progress,
        progress_heartbeat_seconds=0,
    ).run("one")
    assert probe_started.is_set()
    assert phases[0] == "start:hub.layout"
    assert phases[-1] == "ok:hub.layout"


@pytest.mark.asyncio
async def test_runner_emits_heartbeat_while_probe_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phases: list[str] = []

    async def slow_mock_probe(
        name: str,
        context: MockContext,
        *,
        pause_after: bool = False,
    ) -> ProbeOutcome:
        _ = pause_after
        await asyncio.sleep(0.12)
        context.state.operations.append(name)
        return ProbeOutcome(name, "ok")

    monkeypatch.setattr("tests.core.recipes.run_mock_probe", slow_mock_probe)
    monkeypatch.setattr(
        "tests.core.recipes.assert_protected_clients_unchanged",
        _noop_guard,
    )

    async def on_progress(phase: str, metrics: SmokeMetrics) -> None:
        _ = metrics
        phases.append(phase)

    recipes = {
        "one": Recipe("one", "", (RecipeStep(probe="hub.layout", protect_clients=False),))
    }
    await RecipeRunner(
        MockContext(MockDiscordState()),
        recipes,
        backend="mock",
        scheduler=DiscordTestScheduler(phase_delay_seconds=0),
        on_progress=on_progress,
        progress_heartbeat_seconds=0.04,
    ).run("one")
    assert phases[0] == "start:hub.layout"
    assert any(phase == "running:hub.layout" for phase in phases)
    assert phases[-1] == "ok:hub.layout"
