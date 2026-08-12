from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import discord

from bot.contracts.widgets import ButtonSpec, SelectOptionSpec, SelectSpec, recipe_handler
from bot.core.channels.migration import MigrationPlan
from bot.core.text import truncate_external_text
from bot.errors import UserFacingError

# Discord view: up to 5 rows; confirm/cancel occupy one row → at most 4 ambiguous selects.
_MAX_AMBIGUOUS_SELECTS = 4


@dataclass
class MigrationReviewDecision:
    resolutions: dict[str, int] = field(default_factory=dict)
    confirm_deletes: bool = False


def migration_review_embed(plan: MigrationPlan) -> discord.Embed:
    embed = discord.Embed(
        title="Hub migration review",
        description=(
            "Confirm how to map ambiguous channels and whether to remove obsolete "
            "hub leftovers. Client resources are preserved automatically."
        ),
        color=discord.Color.orange(),
    )
    if plan.ambiguous:
        lines = [
            f"`{item.resource_key}` ← {', '.join(f'#{name}' for name in item.candidate_names)}"
            for item in plan.ambiguous
        ]
        embed.add_field(
            name="Ambiguous maps",
            value=truncate_external_text("\n".join(lines), limit=1024),
            inline=False,
        )
    if plan.delete_candidates:
        embed.add_field(
            name="Obsolete channels to remove",
            value=truncate_external_text(
                ", ".join(f"#{item.name}" for item in plan.delete_candidates),
                limit=1024,
            ),
            inline=False,
        )
    return embed


def _require_reviewable_ambiguities(plan: MigrationPlan) -> None:
    count = len(plan.ambiguous)
    if count > _MAX_AMBIGUOUS_SELECTS:
        raise UserFacingError(
            (
                f"Hub migration has **{count}** ambiguous channel maps, but the review UI "
                f"can resolve at most **{_MAX_AMBIGUOUS_SELECTS}** at once. Rename or remove "
                "leftover hub channels to reduce ambiguities, then re-run migration."
            ),
            code="migration_too_many_ambiguous",
        )
    for item in plan.ambiguous:
        if not item.candidate_ids:
            raise UserFacingError(
                (
                    f"Ambiguous resource `{item.resource_key}` has no candidate channels "
                    "to choose from."
                ),
                code="migration_empty_candidates",
            )


async def present_migration_review(
    interaction: discord.Interaction,
    plan: MigrationPlan,
) -> MigrationReviewDecision | None:
    _require_reviewable_ambiguities(plan)
    bot: Any = interaction.client
    selects: list[SelectSpec] = []
    required_keys: set[str] = set()
    candidates: dict[str, set[int]] = {}
    for item in plan.ambiguous:
        options = tuple(
            SelectOptionSpec(
                label=truncate_external_text(name, limit=100),
                value=str(discord_id),
                description=truncate_external_text(f"id {discord_id}", limit=100),
            )
            for discord_id, name in zip(
                item.candidate_ids,
                item.candidate_names,
                strict=True,
            )
        )[:25]
        if not options:
            raise UserFacingError(
                (
                    f"Ambiguous resource `{item.resource_key}` has no displayable "
                    "candidate options."
                ),
                code="migration_empty_candidates",
            )
        required_keys.add(item.resource_key)
        candidates[item.resource_key] = set(item.candidate_ids)
        selects.append(
            SelectSpec(
                tag=item.resource_key,
                placeholder=truncate_external_text(item.resource_key, limit=150),
                options=options,
                handler=recipe_handler("ui.migrate.store", resource_key=item.resource_key),
            )
        )
    built = (
        bot.templates_view("migration_review")
        .fill("ambiguous", tuple(selects))
        .fill(
            "actions",
            (
                ButtonSpec(
                    tag="confirm",
                    label="Confirm",
                    style="danger" if plan.delete_candidates else "primary",
                    handler=recipe_handler("ui.migrate.confirm"),
                ),
                ButtonSpec(
                    tag="cancel",
                    label="Cancel",
                    style="secondary",
                    handler=recipe_handler("ui.migrate.cancel"),
                ),
            ),
        )
        .build(bot)
    )
    built.decision = {}
    built.resolutions = {}
    built.required_keys = required_keys
    built.candidates = candidates
    embed = migration_review_embed(plan)
    send = (
        interaction.followup.send
        if interaction.response.is_done()
        else interaction.response.send_message
    )
    await send(embed=embed, view=built, ephemeral=True)
    message = await interaction.original_response()
    await built.wait()
    if built.decision is None:
        try:
            await message.edit(
                content="Migration review cancelled or timed out.",
                embed=None,
                view=None,
            )
        except discord.HTTPException:
            pass
        return None
    return MigrationReviewDecision(
        resolutions=dict(built.resolutions),
        confirm_deletes=True,
    )
