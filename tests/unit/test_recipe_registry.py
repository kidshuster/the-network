from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.app.recipes.registry import (
    RecipeRegistry,
    RecipeRegistryError,
    recipe,
)
from bot.app.recipes.runtime import RecipeContext


def test_registry_indexes_recipe_metadata() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe("test.operation")
    async def operation(context: RecipeContext) -> str:
        del context
        return "ok"

    registry.register(operation)

    assert registry.spec("test.operation").name == "test.operation"


def test_recipe_required_for_registration() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    async def operation(context: RecipeContext) -> str:
        del context
        return "ok"

    with pytest.raises(RecipeRegistryError, match="not decorated with @recipe"):
        registry.register(operation)


def test_registry_rejects_duplicate_names() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe("test.first")
    async def first(context: RecipeContext) -> None:
        del context

    registry.register(first)
    with pytest.raises(RecipeRegistryError, match="Duplicate recipe"):
        registry.register(first)


def test_registry_rejects_unknown_recipe() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    with pytest.raises(RecipeRegistryError, match="Unknown recipe"):
        registry.spec("missing")


async def test_registry_binds_inputs() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe("test.operation")
    async def operation(context: RecipeContext, *, value: int) -> int:
        del context
        return value * 2

    registry.register(operation)

    assert await registry.run("test.operation", value=4) == 8
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
