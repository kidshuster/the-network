from __future__ import annotations

import contextvars
import inspect
import secrets
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar, cast

from bot.contracts.recipes import (
    RecipeBoundaryError,
    RecipeContext,
    RecipeSpec,
    recipe,
    recipe_spec,
)
from bot.errors import UserFacingError

RecipeFunction = Callable[..., Awaitable[Any]]
F = TypeVar("F", bound=RecipeFunction)
_call_stack: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "recipe_call_stack",
    default=(),
)

__all__ = [
    "RecipeFunction",
    "RecipeRegistry",
    "RecipeRegistryError",
    "RecipeSpec",
    "collect_recipes",
    "recipe",
]


class RecipeRegistryError(RecipeBoundaryError):
    def __init__(
        self,
        message: str,
        *,
        recipe: str | None = None,
        reference: str | None = None,
    ) -> None:
        super().__init__(
            message,
            recipe=recipe,
            reference=reference or secrets.token_hex(4),
        )


class RecipeRegistry:
    def __init__(self, bot: Any) -> None:
        self._bot = bot
        self._recipes: dict[str, RecipeFunction] = {}
        self._specs: dict[str, RecipeSpec] = {}

    def register(self, function: RecipeFunction) -> None:
        spec = recipe_spec(function)
        if spec is None:
            raise RecipeRegistryError(f"{function.__name__} is not decorated with @recipe")
        if spec.name in self._recipes:
            raise RecipeRegistryError(f"Duplicate recipe {spec.name!r}")
        self._recipes[spec.name] = function
        self._specs[spec.name] = spec

    def register_many(self, functions: Iterable[RecipeFunction]) -> None:
        for function in functions:
            self.register(function)

    def has(self, name: str) -> bool:
        return name in self._recipes

    def spec(self, name: str) -> RecipeSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise RecipeRegistryError(f"Unknown recipe {name!r}") from exc

    async def run(self, name: str, **inputs: Any) -> Any:
        try:
            function = self._recipes[name]
        except KeyError as exc:
            raise RecipeRegistryError(f"Unknown recipe {name!r}") from exc
        stack = _call_stack.get()
        if name in stack:
            raise RecipeRegistryError("Recursive recipe call: " + " -> ".join((*stack, name)))
        signature = inspect.signature(function)
        accepts_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
        allowed = {
            key
            for key, param in signature.parameters.items()
            if key != "recipe_context"
            and param.kind
            not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        }
        if not accepts_kwargs:
            unexpected = sorted(set(inputs) - allowed)
            if unexpected:
                raise RecipeRegistryError(
                    f"Unexpected inputs for {name!r}: {unexpected}",
                    recipe=name,
                )
        try:
            signature.bind(RecipeContext(self._bot, self), **inputs)
        except TypeError as exc:
            raise RecipeRegistryError(
                f"Invalid inputs for {name!r}: {exc}",
                recipe=name,
            ) from exc
        token = _call_stack.set((*stack, name))
        try:
            result = await function(RecipeContext(self._bot, self), **inputs)
            if getattr(result, "success", None) is False:
                message = (
                    getattr(result, "error", None)
                    or getattr(result, "reason", None)
                    or f"{name} did not complete successfully."
                )
                raise UserFacingError(str(message))
            return result
        except RecipeRegistryError:
            raise
        except Exception as exc:
            raise RecipeRegistryError(
                f"Recipe {name!r} failed",
                recipe=name,
            ) from exc
        finally:
            _call_stack.reset(token)


def collect_recipes(module: object) -> list[RecipeFunction]:
    return [
        cast(RecipeFunction, value)
        for _, value in inspect.getmembers(module, inspect.iscoroutinefunction)
        if recipe_spec(value) is not None
        and getattr(value, "__module__", None) == getattr(module, "__name__", None)
    ]
