from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.recipes.metadata import CommandSpec
from bot.recipes.registry import RecipeRegistry, RecipeRegistryError, recipe
from bot.recipes.runtime import RecipeContext


def test_registry_indexes_recipe_metadata() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe(
        "test.operation",
        command=CommandSpec("test", "operation", "Run operation"),
        events=("test.event",),
        interactions=("test:button",),
    )
    async def operation(context: RecipeContext) -> str:
        del context
        return "ok"

    registry.register(operation)

    assert registry.spec("test.operation").command is not None
    assert registry.recipes_for_event("test.event") == ("test.operation",)
    assert registry.recipe_for_interaction("test:button") == "test.operation"
    assert registry.command_specs() == (registry.spec("test.operation"),)


def test_registry_rejects_duplicate_names_and_interactions() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe("test.first", interactions=("test:button",))
    async def first(context: RecipeContext) -> None:
        del context

    @recipe("test.second", interactions=("test:button",))
    async def second(context: RecipeContext) -> None:
        del context

    registry.register(first)
    with pytest.raises(RecipeRegistryError, match="Duplicate recipe"):
        registry.register(first)
    with pytest.raises(RecipeRegistryError, match="Interaction.*already registered"):
        registry.register(second)


def test_registry_rejects_unknown_recipe_event_and_interaction() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    assert registry.recipes_for_event("missing") == ()
    with pytest.raises(RecipeRegistryError, match="Unknown recipe"):
        registry.spec("missing")
    with pytest.raises(RecipeRegistryError, match="Unknown interaction"):
        registry.recipe_for_interaction("missing")


async def test_registry_binds_inputs_and_dispatches_events() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe("test.operation", events=("test.event",))
    async def operation(context: RecipeContext, *, value: int) -> int:
        del context
        return value * 2

    registry.register(operation)

    assert await registry.run("test.operation", value=4) == 8
    assert await registry.dispatch("test.event", value=5) == [10]
    with pytest.raises(RecipeRegistryError, match="Invalid inputs"):
        await registry.run("test.operation")


async def test_registry_supports_nested_calls_and_rejects_cycles() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe("test.child")
    async def child(context: RecipeContext, *, value: int) -> int:
        del context
        return value * 2

    @recipe("test.parent")
    async def parent(context: RecipeContext, *, value: int) -> int:
        return await context.run("test.child", value=value + 1)

    @recipe("test.loop")
    async def loop(context: RecipeContext) -> None:
        await context.run("test.loop")

    registry.register_many((child, parent, loop))

    assert await registry.run("test.parent", value=2) == 6
    with pytest.raises(RecipeRegistryError, match="Recursive recipe call"):
        await registry.run("test.loop")


async def test_registry_preserves_recipe_boundary_and_cause() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe("test.failure")
    async def failure(context: RecipeContext) -> None:
        del context
        raise ValueError("bad state")

    registry.register(failure)

    with pytest.raises(RecipeRegistryError, match="test.failure") as raised:
        await registry.run("test.failure")
    assert isinstance(raised.value.__cause__, ValueError)
    assert str(raised.value.__cause__) == "bad state"
