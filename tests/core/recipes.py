from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from tests.core.client_guard import assert_protected_clients_unchanged
from tests.core.live_backend import run_live_probe
from tests.core.mock_backend import MockContext, run_mock_probe
from tests.core.probes import LiveContext, ProbeOutcome

RECIPE_DIR = Path(__file__).resolve().parents[1] / "recipes"


@dataclass(frozen=True)
class RecipeStep:
    probe: str | None = None
    recipe: str | None = None
    pause: bool = False
    protect_clients: bool = True


@dataclass(frozen=True)
class Recipe:
    name: str
    description: str
    steps: tuple[RecipeStep, ...]
    finally_steps: tuple[RecipeStep, ...] = ()


def _step(raw: Any, *, source: Path) -> RecipeStep:
    if isinstance(raw, str):
        return RecipeStep(probe=raw)
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: recipe step must be a string or mapping")
    probe = raw.get("probe")
    recipe = raw.get("recipe")
    if (probe is None) == (recipe is None):
        raise ValueError(f"{source}: step must define exactly one of probe or recipe")
    return RecipeStep(
        probe=str(probe) if probe is not None else None,
        recipe=str(recipe) if recipe is not None else None,
        pause=bool(raw.get("pause", False)),
        protect_clients=bool(raw.get("protect_clients", True)),
    )


def load_recipes(directory: Path = RECIPE_DIR) -> dict[str, Recipe]:
    recipes: dict[str, Recipe] = {}
    for path in sorted(directory.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"{path}: root must be a mapping")
        name = str(payload.get("name", path.stem))
        if name in recipes:
            raise ValueError(f"Duplicate live recipe {name!r}")
        recipes[name] = Recipe(
            name=name,
            description=str(payload.get("description", "")),
            steps=tuple(_step(raw, source=path) for raw in payload.get("steps", [])),
            finally_steps=tuple(
                _step(raw, source=path) for raw in payload.get("finally", [])
            ),
        )
    return recipes


Backend = Literal["live", "mock"]


class RecipeRunner:
    def __init__(
        self,
        context: LiveContext | MockContext,
        recipes: dict[str, Recipe],
        *,
        backend: Backend = "live",
    ) -> None:
        self.context = context
        self.recipes = recipes
        self.backend = backend
        self.outcomes: list[ProbeOutcome] = []

    async def run(self, name: str) -> list[ProbeOutcome]:
        await self._run_recipe(name, stack=())
        return list(self.outcomes)

    async def run_probe(self, name: str) -> ProbeOutcome:
        return await self._run_probe(name, protect_clients=True, pause=False)

    async def _run_recipe(self, name: str, *, stack: tuple[str, ...]) -> None:
        if name in stack:
            raise ValueError("Live recipe cycle: " + " -> ".join((*stack, name)))
        try:
            recipe = self.recipes[name]
        except KeyError as exc:
            raise KeyError(f"Unknown live recipe {name!r}") from exc
        print(f"\n==> {recipe.name}: {recipe.description}", flush=True)
        try:
            for step in recipe.steps:
                await self._run_step(step, stack=(*stack, name))
        finally:
            for step in recipe.finally_steps:
                await self._run_step(step, stack=(*stack, name))

    async def _run_step(self, step: RecipeStep, *, stack: tuple[str, ...]) -> None:
        if step.recipe is not None:
            await self._run_recipe(step.recipe, stack=stack)
            return
        assert step.probe is not None
        await self._run_probe(
            step.probe,
            protect_clients=step.protect_clients,
            pause=step.pause,
        )

    async def _run_probe(
        self, name: str, *, protect_clients: bool, pause: bool
    ) -> ProbeOutcome:
        print(f"  RUN  {name}", flush=True)
        if self.backend == "mock":
            if not isinstance(self.context, MockContext):
                raise TypeError("mock backend requires MockContext")
            outcome = await run_mock_probe(name, self.context, pause_after=pause)
        else:
            if not isinstance(self.context, LiveContext):
                raise TypeError("live backend requires LiveContext")
            outcome = await run_live_probe(name, self.context, pause_after=pause)
        self.outcomes.append(outcome)
        print(f"  OK   {name}: {outcome.detail}", flush=True)
        if (
            self.backend == "live"
            and protect_clients
            and name not in {"clients.protected", "artifacts.teardown"}
        ):
            assert isinstance(self.context, LiveContext)
            await assert_protected_clients_unchanged(
                self.context.guild,
                self.context.runtime,
                self.context.protected_clients,
                phase=name,
            )
        return outcome
