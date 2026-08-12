from __future__ import annotations

# Explicit Discord allowlist — not the full YAML catalog.
ALLOWED_SMOKE_RECIPES: dict[str, bool] = {
    # recipe_name -> requires_confirmation (destructive)
    "full": True,
    "functional": True,
    "server-init-stress": True,
    "server-init-audit": False,
    "clean": True,
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

ALL_SCENARIOS_CHOICE = "all"


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
    if value == ALL_SCENARIOS_CHOICE:
        return ALL_SCENARIOS_CHOICE
    if value not in ALLOWED_SCENARIOS:
        raise ValueError(
            "Unsupported scenario. Allowed: "
            + ", ".join([ALL_SCENARIOS_CHOICE, *sorted(ALLOWED_SCENARIOS)])
        )
    return value


def expand_scenarios(scenario: str) -> tuple[str, ...]:
    """Expand a scenario choice into concrete scenario names to run."""
    name = validate_scenario_choice(scenario)
    if name != ALL_SCENARIOS_CHOICE:
        return (name,)
    # Healthy first, then remaining scenarios alphabetically.
    rest = sorted(s for s in ALLOWED_SCENARIOS if s != "healthy")
    return ("healthy", *rest)


def expand_scenarios_for_recipe(recipe: str, scenario: str) -> tuple[str, ...]:
    """Expand scenarios for a recipe; cleanup runs once regardless of matrix choice."""
    if validate_recipe_choice(recipe) == "clean":
        return ("healthy",)
    return expand_scenarios(scenario)


def requires_confirmation(recipe: str) -> bool:
    return bool(ALLOWED_SMOKE_RECIPES[validate_recipe_choice(recipe)])


def allowed_recipe_names() -> list[str]:
    return sorted(ALLOWED_SMOKE_RECIPES)


def allowed_scenario_names() -> list[str]:
    return [ALL_SCENARIOS_CHOICE, *sorted(ALLOWED_SCENARIOS)]
