from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.live.mock_backend import MockContext, MockDiscordState, load_mock_context
from tests.live.probes import PROBES, ProbeOutcome
from tests.live.recipes import Recipe, RecipeRunner, RecipeStep, load_recipes


def test_shipped_recipes_only_reference_registered_probes_and_recipes() -> None:
    recipes = load_recipes()
    assert {
        "audit",
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

    monkeypatch.setattr("tests.live.recipes.run_mock_probe", fake_mock_probe)
    monkeypatch.setattr(
        "tests.live.recipes.assert_protected_clients_unchanged",
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
    assert "hub.rebuild" in context.state.operations


@pytest.mark.asyncio
async def test_mock_functional_recipe_rectifies_stale_permissions() -> None:
    context = load_mock_context("stale_permissions")
    assert not context.state.leaders_access
    await RecipeRunner(context, load_recipes(), backend="mock").run("functional")
    assert context.state.leaders_access


@pytest.mark.asyncio
async def test_mock_audit_exposes_missing_layout() -> None:
    context = load_mock_context("missing_layout")
    with pytest.raises(RuntimeError, match="moderator-only channel is missing"):
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
