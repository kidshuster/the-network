from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Awaitable[object]])

_SPEC_ATTRIBUTE = "__network_recipe_spec__"


@dataclass(frozen=True)
class RecipeSpec:
    name: str


class RecipeBoundaryError(RuntimeError):
    """Raised at the recipe registry boundary; safe for features to catch."""

    recipe: str | None
    reference: str

    def __init__(
        self,
        message: str,
        *,
        recipe: str | None = None,
        reference: str | None = None,
    ) -> None:
        super().__init__(message)
        self.recipe = recipe
        self.reference = reference or "none"


@dataclass(frozen=True)
class RecipeContext:
    """Opaque recipe execution context shared across the feature boundary.

    ``bot`` and ``registry`` are runtime objects owned by ``app``. Features must
    treat them as duck-typed capabilities, not import ``bot.app`` types.
    """

    bot: Any
    registry: Any

    @property
    def core(self) -> Any:
        context = self.bot.bot_context
        if context is None:
            raise RuntimeError("Bot context is not initialized")
        return context

    async def run(self, recipe: str, **inputs: Any) -> Any:
        return await self.registry.run(recipe, **inputs)


def recipe(name: str) -> Callable[[F], F]:
    """Attach recipe metadata. Registry/execution remain in ``bot.app.recipes``."""

    def decorate(function: F) -> F:
        setattr(function, _SPEC_ATTRIBUTE, RecipeSpec(name))
        return function

    return decorate


def recipe_spec(function: object) -> RecipeSpec | None:
    spec = getattr(function, _SPEC_ATTRIBUTE, None)
    return spec if isinstance(spec, RecipeSpec) else None
