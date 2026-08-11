from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.core.runtime import BotContext
    from bot.widgets.recipes.registry import RecipeRegistry


@dataclass(frozen=True)
class RecipeContext:
    bot: NetworkRelayBot
    registry: RecipeRegistry

    @property
    def core(self) -> BotContext:
        context = self.bot.bot_context
        if context is None:
            raise RuntimeError("Bot context is not initialized")
        return context

    async def run(self, recipe: str, **inputs: Any) -> Any:
        return await self.registry.run(recipe, **inputs)
