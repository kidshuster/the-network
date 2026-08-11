from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.live.probes import PROBES, ProbeOutcome
from tests.live.recipes import Recipe, RecipeRunner, RecipeStep, load_recipes


def test_shipped_recipes_only_reference_registered_probes_and_recipes() -> None:
    recipes = load_recipes()
    assert {"audit", "functional", "full", "stress"} <= recipes.keys()
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

    monkeypatch.setattr("tests.live.recipes.get_probe", lambda _name: fake_probe)
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
    runner = RecipeRunner(object(), recipes)  # type: ignore[arg-type]
    await runner.run("parent")
    assert calls == ["probe", "probe"]


@pytest.mark.asyncio
async def test_runner_rejects_recipe_cycles() -> None:
    recipes = {
        "a": Recipe("a", "", (RecipeStep(recipe="b"),)),
        "b": Recipe("b", "", (RecipeStep(recipe="a"),)),
    }
    runner = RecipeRunner(object(), recipes)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="a -> b -> a"):
        await runner.run("a")


async def _noop_guard(*_args: Any, **_kwargs: Any) -> None:
    return None
