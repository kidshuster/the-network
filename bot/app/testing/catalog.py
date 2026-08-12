from __future__ import annotations

# Explicit Discord allowlist — not the full YAML catalog.
ALLOWED_SMOKE_RECIPES: dict[str, bool] = {
    # recipe_name -> requires_confirmation (destructive)
    "full": True,
    "functional": True,
    "server-init-stress": True,
    "server-init-audit": False,
}

ALLOWED_SCENARIOS: frozenset[str] = frozenset(
    {
        "healthy",
        "stale_permissions",
        "malformed_channels",
        "missing_layout",
        "hard_blocker",
    }
)


def validate_recipe_choice(recipe: str) -> str:
    name = recipe.strip()
    if name not in ALLOWED_SMOKE_RECIPES:
        raise ValueError(
            "Unsupported smoke recipe. Allowed: "
            + ", ".join(sorted(ALLOWED_SMOKE_RECIPES))
        )
    return name


def validate_scenario_choice(scenario: str | None) -> str:
    value = (scenario or "healthy").strip() or "healthy"
    if value not in ALLOWED_SCENARIOS:
        raise ValueError(
            "Unsupported scenario. Allowed: " + ", ".join(sorted(ALLOWED_SCENARIOS))
        )
    return value


def requires_confirmation(recipe: str) -> bool:
    return bool(ALLOWED_SMOKE_RECIPES[validate_recipe_choice(recipe)])


def allowed_recipe_names() -> list[str]:
    return sorted(ALLOWED_SMOKE_RECIPES)
