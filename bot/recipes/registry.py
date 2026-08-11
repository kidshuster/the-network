from __future__ import annotations

import contextvars
import inspect
import secrets
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar, cast

from bot.errors import UserFacingError
from bot.recipes.metadata import CommandSpec, RecipeSpec
from bot.recipes.runtime import RecipeContext

RecipeFunction = Callable[..., Awaitable[Any]]
F = TypeVar("F", bound=RecipeFunction)
_SPEC_ATTRIBUTE = "__network_recipe_spec__"
_call_stack: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "recipe_call_stack",
    default=(),
)


class RecipeRegistryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        recipe: str | None = None,
        reference: str | None = None,
    ) -> None:
        super().__init__(message)
        self.recipe = recipe
        self.reference = reference or secrets.token_hex(4)


def recipe(
    name: str,
    *,
    command: CommandSpec | None = None,
    events: tuple[str, ...] = (),
    interactions: tuple[str, ...] = (),
) -> Callable[[F], F]:
    def decorate(function: F) -> F:
        setattr(
            function,
            _SPEC_ATTRIBUTE,
            RecipeSpec(name, command, events, interactions),
        )
        return function

    return decorate


class RecipeRegistry:
    def __init__(self, bot: Any) -> None:
        self._bot = bot
        self._recipes: dict[str, RecipeFunction] = {}
        self._specs: dict[str, RecipeSpec] = {}
        self._events: dict[str, list[str]] = defaultdict(list)
        self._interactions: dict[str, str] = {}

    def register(self, function: RecipeFunction) -> None:
        spec = getattr(function, _SPEC_ATTRIBUTE, None)
        if not isinstance(spec, RecipeSpec):
            raise RecipeRegistryError(f"{function.__name__} is not decorated with @recipe")
        if spec.name in self._recipes:
            raise RecipeRegistryError(f"Duplicate recipe {spec.name!r}")
        for interaction in spec.interactions:
            if interaction in self._interactions:
                owner = self._interactions[interaction]
                raise RecipeRegistryError(
                    f"Interaction {interaction!r} is already registered by {owner!r}"
                )
        self._recipes[spec.name] = function
        self._specs[spec.name] = spec
        for event in spec.events:
            self._events[event].append(spec.name)
        for interaction in spec.interactions:
            self._interactions[interaction] = spec.name

    def register_many(self, functions: Iterable[RecipeFunction]) -> None:
        for function in functions:
            self.register(function)

    def spec(self, name: str) -> RecipeSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise RecipeRegistryError(f"Unknown recipe {name!r}") from exc

    def recipes_for_event(self, event: str) -> tuple[str, ...]:
        return tuple(self._events.get(event, ()))

    def recipe_for_interaction(self, interaction: str) -> str:
        try:
            return self._interactions[interaction]
        except KeyError as exc:
            raise RecipeRegistryError(f"Unknown interaction {interaction!r}") from exc

    def command_specs(self) -> tuple[RecipeSpec, ...]:
        return tuple(spec for spec in self._specs.values() if spec.command is not None)

    async def run(self, name: str, **inputs: Any) -> Any:
        try:
            function = self._recipes[name]
        except KeyError as exc:
            raise RecipeRegistryError(f"Unknown recipe {name!r}") from exc
        stack = _call_stack.get()
        if name in stack:
            raise RecipeRegistryError("Recursive recipe call: " + " -> ".join((*stack, name)))
        signature = inspect.signature(function)
        try:
            signature.bind(RecipeContext(self._bot, self), **inputs)
        except TypeError as exc:
            raise RecipeRegistryError(f"Invalid inputs for {name!r}: {exc}") from exc
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

    async def dispatch(self, event: str, **inputs: Any) -> list[Any]:
        return [await self.run(name, **inputs) for name in self.recipes_for_event(event)]


def collect_recipes(module: object) -> list[RecipeFunction]:
    return [
        cast(RecipeFunction, value)
        for _, value in inspect.getmembers(module, inspect.iscoroutinefunction)
        if isinstance(getattr(value, _SPEC_ATTRIBUTE, None), RecipeSpec)
    ]
